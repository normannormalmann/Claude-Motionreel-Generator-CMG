"""Spielt ein Update ein, nachdem sich das Studio beendet hat, und startet es danach neu.

Aufruf (durch das Studio):  python update_runner.py <app-daten-ordner> <studio-ordner> <app-ordner> <commit>

Lädt den Installer aus genau dem geprüften Commit und führt ihn ohne Rückfragen aus; der Installer
holt über CMG_REF alle weiteren Dateien aus demselben Commit. Das Studio wird in jedem Fall wieder
gestartet – auch wenn das Update scheitert. Es meldet dann das Ergebnis aus update-result.json.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import platform_support as ps  # noqa: E402
from updates import MANIFEST_NAME, ManifestError, load_manifest, read_limited, repository_urls, validate_commit  # noqa: E402

STUDIO_EXIT_TIMEOUT = 60
INSTALL_TIMEOUT_SECONDS = 45 * 60
MAX_INSTALLER_BYTES = 2 * 1024 * 1024
LOCK_MAX_AGE_SECONDS = 2 * 60 * 60
INSTALLER_NAME = "install.ps1" if ps.IS_WINDOWS else "install.sh"


class AlreadyRunningError(Exception):
    """Ein anderer Update-Helfer arbeitet bereits."""


def acquire_lock(data_dir):
    """Verhindert, dass zwei Updates gleichzeitig laufen (z. B. nach einem Doppelklick)."""
    lock = Path(data_dir) / "update.lock"
    for _ in range(2):
        try:
            handle = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime < LOCK_MAX_AGE_SECONDS:
                    raise AlreadyRunningError()
                lock.unlink()  # Überbleibsel eines abgestürzten Updates
            except FileNotFoundError:
                pass
            continue
        os.write(handle, str(os.getpid()).encode("ascii"))
        os.close(handle)
        return lock
    raise AlreadyRunningError()


def wait_for_studio_exit(data_dir, timeout=STUDIO_EXIT_TIMEOUT):
    """Das Studio löscht server.json beim Beenden."""
    deadline = time.time() + timeout
    while (Path(data_dir) / "server.json").exists() and time.time() < deadline:
        time.sleep(0.5)


def download_installer(target_dir, commit):
    raw_base, _ = repository_urls()
    target = Path(target_dir) / INSTALLER_NAME
    target.write_bytes(read_limited("{}/{}/{}".format(raw_base, commit, INSTALLER_NAME), MAX_INSTALLER_BYTES))
    return target


def _kill_tree(process):
    if ps.IS_WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True,
                       **ps.hidden_process_flags())
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


def run_installer(installer, studio_dir, log_file, commit):
    env = dict(ps.tool_environment(), CMG_NONINTERACTIVE="1", CMG_UPDATE="1", CMG_REF=commit,
               CMG_STUDIO_DIR=str(studio_dir), CMG_LOG_FILE=str(log_file))
    if ps.IS_WINDOWS:
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer)]
        group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    else:
        args = ["bash", str(installer)]
        group = {"start_new_session": True}
    process = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, **group)
    try:
        return process.wait(timeout=INSTALL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        # Auch pip, npm und Playwright beenden, bevor das Studio neu startet.
        _kill_tree(process)
        process.wait()
        raise


def restart_studio(app_dir):
    python = Path(sys.executable)
    if ps.IS_WINDOWS:
        # Ohne Konsolenfenster wie über die Desktop-Verknüpfung.
        windowed = python.with_name("pythonw.exe")
        python = windowed if windowed.exists() else python
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    else:
        options = {"start_new_session": True}
    subprocess.Popen([str(python), str(Path(app_dir) / "studio_app.py")], cwd=str(app_dir),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env=ps.tool_environment(), **options)


def _write_result(data_dir, app_dir, ok, message, log_file):
    manifest = load_manifest(Path(app_dir) / MANIFEST_NAME)
    result = {"ok": ok, "finished_at": time.time(), "version": manifest and manifest["cmg"],
              "message": message, "log": str(log_file)}
    (Path(data_dir) / "update-result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def run_update(data_dir, studio_dir, app_dir, commit, download=download_installer, install=run_installer,
               restart=restart_studio, wait=wait_for_studio_exit):
    data_dir, app_dir = Path(data_dir), Path(app_dir)
    log_file = data_dir / "update-install.log"
    lock = acquire_lock(data_dir)  # läuft schon ein Update, startet das andere das Studio neu
    temp = None
    ok, message = False, "Das Update wurde unterbrochen."
    try:
        wait(data_dir)
        temp = tempfile.mkdtemp(prefix="cmg-update-")
        installer = download(temp, validate_commit(commit))
        ok = install(installer, studio_dir, log_file, commit) == 0
        message = None if ok else "Der Installer hat mit einem Fehler aufgehört."
    except subprocess.TimeoutExpired:
        message = "Das Update hat zu lange gedauert und wurde abgebrochen."
    except Exception as error:  # noqa: BLE001 – jeder Fehler soll gemeldet werden, das Studio muss zurückkommen
        message = "Das Update konnte nicht ausgeführt werden ({}).".format(type(error).__name__)
    finally:
        try:
            result = _write_result(data_dir, app_dir, ok, message, log_file)
        finally:
            if temp:
                shutil.rmtree(temp, ignore_errors=True)
            lock.unlink(missing_ok=True)
            restart(app_dir)
    return result


def main(argv):
    if len(argv) != 5:
        print(__doc__.strip().splitlines()[2].strip())
        return 1
    try:
        validate_commit(argv[4])
    except ManifestError:
        return 1
    try:
        return 0 if run_update(argv[1], argv[2], argv[3], argv[4])["ok"] else 1
    except AlreadyRunningError:
        return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main(sys.argv))
