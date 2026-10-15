"""Betriebssystem-Hilfen: Pfade, Programmsuche, Ordner öffnen."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
APP_NAME = "Claude-Motion-Studio"


def app_data_dir():
    """Ordner für App-Zustand (außerhalb von Dokumente, damit er nicht synchronisiert wird)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "claude-motion-studio"
    base.mkdir(parents=True, exist_ok=True)
    if not IS_WINDOWS:
        # Gesprächsverlauf und Startkennung nur für den eigenen Benutzer lesbar.
        os.chmod(base, 0o700)
    return base


def _windows_documents_dir():
    import ctypes
    from ctypes import wintypes

    buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    csidl_personal = 5
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl_personal, None, 0, buffer)
    return Path(buffer.value) if buffer.value else Path.home() / "Documents"


def _linux_documents_dir():
    try:
        output = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=5)
        candidate = output.stdout.strip()
        if candidate and Path(candidate) != Path.home():
            return Path(candidate)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Documents"


def studio_dir():
    """Studio-Ordner: vom Installer gespeichert, sonst Dokumente/Claude-Motion-Studio."""
    config_file = app_data_dir() / "config.json"
    if config_file.exists():
        try:
            configured = json.loads(config_file.read_text(encoding="utf-8")).get("studio_dir")
            if configured:
                return Path(configured)
        except (OSError, ValueError):
            pass
    if os.environ.get("CMG_STUDIO_DIR"):
        return Path(os.environ["CMG_STUDIO_DIR"])
    if IS_WINDOWS:
        documents = _windows_documents_dir()
    elif IS_MAC:
        documents = Path.home() / "Documents"
    else:
        documents = _linux_documents_dir()
    return documents / APP_NAME


def _windows_registry_path():
    import winreg

    parts = []
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, r"Environment"),
    )
    for hive, key_path in locations:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                parts.append(os.path.expandvars(value))
        except OSError:
            continue
    return os.pathsep.join(parts)


def tool_environment():
    """Umgebung für Claude & Co.: PATH aufgefrischt, damit frisch installierte Programme gefunden werden."""
    env = dict(os.environ)
    home = Path.home()
    extra = [str(home / ".local" / "bin")]
    if IS_WINDOWS:
        extra.append(_windows_registry_path())
        extra.append(str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"))
    else:
        extra += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def claude_command():
    """Befehl zum Starten von Claude Code als Liste (für Tests über CMG_CLAUDE_BIN austauschbar)."""
    override = os.environ.get("CMG_CLAUDE_BIN")
    if override:
        return [sys.executable, override] if override.endswith(".py") else [override]
    found = shutil.which("claude", path=tool_environment()["PATH"])
    return [found] if found else None


def hidden_process_flags():
    """Verhindert unter Windows aufblitzende Konsolenfenster."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}


def open_in_file_manager(path):
    path = str(path)
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606 – öffnet den Explorer
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
