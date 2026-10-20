"""Tests für die Update-Prüfung (updates.py) und den Update-Helfer (update_runner.py)."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio-app"))

import update_runner  # noqa: E402
import updates  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"
INSTALLED = {"cmg": "1.1.0", "codex": "0.162.1",
             "python_packages": {"playwright": "1.64.0", "pillow": "13.0.0", "numpy": "2.5.4"}}
NEWER = {"cmg": "1.1.1", "codex": "0.163.0",
         "python_packages": {"playwright": "1.64.0", "pillow": "13.0.0", "numpy": "2.5.5"}}


class FakeRemote:
    def __init__(self, manifest=None, error=None):
        self.manifest, self.error, self.calls = manifest, error, 0

    def __call__(self):
        self.calls += 1
        if self.error:
            raise self.error
        return updates.validate_manifest(self.manifest), COMMIT


def make_dirs(test):
    temp = tempfile.TemporaryDirectory()
    test.addCleanup(temp.cleanup)
    base = Path(temp.name)
    test.app, test.data, test.studio = base / "app", base / "data", base / "studio"
    for folder in (test.app, test.data, test.studio):
        folder.mkdir()


class UpdateCheckerTests(unittest.TestCase):
    def setUp(self):
        make_dirs(self)
        (self.app / "versions.json").write_text(json.dumps(INSTALLED), encoding="utf-8")
        self.launched = []

    def checker(self, remote):
        return updates.UpdateChecker(self.app, self.data, self.studio, fetch=remote,
                                     launch=lambda args, log: self.launched.append((args, log)))

    def test_manifest_validation_rejects_bad_values(self):
        updates.validate_manifest(INSTALLED)
        for broken in ({}, dict(INSTALLED, cmg="1.0; rm -rf"), dict(INSTALLED, codex=None),
                       dict(INSTALLED, python_packages={"--index-url": "1.0.0"}),
                       dict(INSTALLED, python_packages={"numpy": "2.5.5 --pre"}),
                       dict(INSTALLED, cmg="1.0.0\n"), []):
            with self.assertRaises(updates.ManifestError):
                updates.validate_manifest(broken)

    def test_commit_validation(self):
        self.assertEqual(updates.validate_commit(COMMIT), COMMIT)
        for broken in ("main", COMMIT.upper(), COMMIT + "0", "--ref=x", None):
            with self.assertRaises(updates.ManifestError):
                updates.validate_commit(broken)

    def test_test_server_override_only_for_local_addresses(self):
        for value, expected in (("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
                                ("http://localhost", "http://localhost"),
                                ("https://evil.example", updates.GITHUB_RAW),
                                ("file:///etc", updates.GITHUB_RAW),
                                ("http://127.0.0.1.evil.example", updates.GITHUB_RAW)):
            with mock.patch.dict(os.environ, {"CMG_REPO_RAW": value}):
                self.assertEqual(updates.repository_urls()[0], expected, value)

    def test_versions_compare_numerically(self):
        self.assertGreater(updates.parse_version("1.10.0"), updates.parse_version("1.9.9"))

    def test_newer_remote_version_is_offered_with_changes(self):
        status = self.checker(FakeRemote(NEWER)).status()
        self.assertTrue(status["available"])
        self.assertEqual((status["current"], status["latest"]), ("1.1.0", "1.1.1"))
        self.assertEqual([(c["name"], c["from"], c["to"]) for c in status["changes"]],
                         [("Motion Studio", "1.1.0", "1.1.1"), ("Codex (ChatGPT)", "0.162.1", "0.163.0"),
                          ("Numpy", "2.5.4", "2.5.5")])

    def test_same_or_older_remote_version_is_not_offered(self):
        self.assertFalse(self.checker(FakeRemote(INSTALLED)).status()["available"])
        older = dict(INSTALLED, cmg="1.0.9")
        self.assertFalse(self.checker(FakeRemote(older)).status()["available"])

    def test_remote_is_checked_at_most_once_a_day_unless_forced(self):
        remote = FakeRemote(NEWER)
        checker = self.checker(remote)
        checker.status()
        checker.status()
        self.assertEqual(remote.calls, 1)
        checker.status(force=True)
        self.assertEqual(remote.calls, 2)
        cache = json.loads(checker.cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cache["commit"], COMMIT)
        cache["checked_at"] = time.time() - updates.CHECK_INTERVAL_SECONDS - 1
        checker.cache_file.write_text(json.dumps(cache), encoding="utf-8")
        checker.status()
        self.assertEqual(remote.calls, 3)

    def test_offline_keeps_last_known_state_but_does_not_start(self):
        self.checker(FakeRemote(NEWER)).status()
        cache = json.loads((self.data / "update-check.json").read_text(encoding="utf-8"))
        cache["checked_at"] = 0
        (self.data / "update-check.json").write_text(json.dumps(cache), encoding="utf-8")
        offline = self.checker(FakeRemote(error=OSError("offline")))
        status = offline.status()
        self.assertTrue(status["available"])
        self.assertEqual(status["error"], "OSError")
        with self.assertRaises(updates.UpdateUnavailableError):
            offline.start()
        self.assertEqual(self.launched, [])

    def test_offline_without_cache_offers_nothing(self):
        self.assertFalse(self.checker(FakeRemote(error=OSError("offline"))).status()["available"])

    def test_check_can_be_disabled(self):
        remote = FakeRemote(NEWER)
        checker = self.checker(remote)
        checker.enabled = False
        self.assertFalse(checker.status()["available"])
        self.assertEqual(remote.calls, 0)

    def test_update_result_stays_until_acknowledged(self):
        checker = self.checker(FakeRemote(INSTALLED))
        checker.result_file.write_text(json.dumps({"ok": True, "version": "1.1.1", "evil": "<b>"}), encoding="utf-8")
        self.assertEqual(checker.status()["result"], {"ok": True, "version": "1.1.1"})
        self.assertEqual(checker.status()["result"], {"ok": True, "version": "1.1.1"})
        checker.acknowledge_result()
        self.assertIsNone(checker.status()["result"])

    def test_start_launches_runner_for_the_checked_commit(self):
        with self.assertRaises(updates.UpdateUnavailableError):
            self.checker(FakeRemote(INSTALLED)).start()
        self.assertEqual(self.launched, [])
        self.checker(FakeRemote(NEWER)).start()
        args, log = self.launched[0]
        self.assertEqual(Path(args[1]).name, "update_runner.py")
        self.assertEqual(args[2:], [str(self.data), str(self.studio), str(self.app), COMMIT])
        self.assertEqual(log, self.data / "update-runner.log")


class UpdateRunnerTests(unittest.TestCase):
    def setUp(self):
        make_dirs(self)
        self.restarted = []
        self.downloads = []

    def default_download(self, target, commit):
        self.downloads.append(commit)
        path = Path(target) / "install.sh"
        path.write_text("echo", encoding="utf-8")
        return path

    def default_install(self, installer, studio, log, commit):
        (self.app / "versions.json").write_text(json.dumps(NEWER), encoding="utf-8")
        return 0

    def run_update(self, install=None, download=None, wait=None):
        return update_runner.run_update(
            self.data, self.studio, self.app, COMMIT, download=download or self.default_download,
            install=install or self.default_install, restart=self.restarted.append,
            wait=wait or (lambda data: None),
        )

    def stored_result(self):
        return json.loads((self.data / "update-result.json").read_text(encoding="utf-8"))

    def test_successful_update_records_new_version_and_restarts(self):
        result = self.run_update()
        self.assertTrue(result["ok"])
        self.assertEqual(self.downloads, [COMMIT])
        self.assertEqual(self.stored_result()["version"], "1.1.1")
        self.assertEqual(self.restarted, [self.app])
        self.assertFalse((self.data / "update.lock").exists())

    def test_failed_installer_is_reported_and_studio_still_restarts(self):
        self.assertFalse(self.run_update(install=lambda *args: 1)["ok"])
        self.assertIn("Fehler", self.stored_result()["message"])
        self.assertEqual(self.restarted, [self.app])

    def test_any_error_is_reported_and_studio_still_restarts(self):
        for error in (OSError("offline"), ValueError("kaputt"), RuntimeError("unerwartet")):
            def broken(target, commit, error=error):
                raise error

            self.restarted.clear()
            self.assertFalse(self.run_update(download=broken)["ok"])
            self.assertIn(type(error).__name__, self.stored_result()["message"])
            self.assertEqual(self.restarted, [self.app])

    def test_error_while_waiting_still_restarts(self):
        def broken_wait(data):
            raise OSError("weg")

        self.assertFalse(self.run_update(wait=broken_wait)["ok"])
        self.assertEqual(self.restarted, [self.app])

    def test_timeout_is_reported(self):
        def slow(*args):
            raise subprocess.TimeoutExpired("installer", 1)

        self.assertFalse(self.run_update(install=slow)["ok"])
        self.assertIn("zu lange", self.stored_result()["message"])

    def test_second_runner_does_not_run_concurrently(self):
        lock = update_runner.acquire_lock(self.data)
        with self.assertRaises(update_runner.AlreadyRunningError):
            self.run_update()
        self.assertEqual(self.restarted, [])
        lock.unlink()
        stale = update_runner.acquire_lock(self.data)
        old = time.time() - update_runner.LOCK_MAX_AGE_SECONDS - 10
        os.utime(stale, (old, old))
        self.assertTrue(self.run_update()["ok"])

    def test_invalid_commit_is_rejected(self):
        self.assertEqual(update_runner.main(["x", str(self.data), str(self.studio), str(self.app), "main"]), 1)
        self.assertEqual(self.restarted, [])

    def test_installer_gets_update_mode_commit_and_studio_folder(self):
        seen = {}

        class FakeProcess:
            pid = 4242

            def wait(self, timeout=None):
                return 0

        def fake_popen(args, env, **kwargs):
            seen.update(args=args, env=env, kwargs=kwargs)
            return FakeProcess()

        with mock.patch.object(update_runner.subprocess, "Popen", fake_popen):
            update_runner.run_installer(Path("inst"), self.studio, self.data / "log.txt", COMMIT)
        self.assertEqual(seen["env"]["CMG_UPDATE"], "1")
        self.assertEqual(seen["env"]["CMG_NONINTERACTIVE"], "1")
        self.assertEqual(seen["env"]["CMG_REF"], COMMIT)
        self.assertEqual(seen["env"]["CMG_STUDIO_DIR"], str(self.studio))

    def test_installer_tree_is_killed_on_timeout(self):
        killed = []

        class HangingProcess:
            pid = 4242

            def __init__(self):
                self.calls = 0

            def wait(self, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired("installer", timeout)
                return -9

        with mock.patch.object(update_runner.subprocess, "Popen", lambda *a, **k: HangingProcess()), \
                mock.patch.object(update_runner, "_kill_tree", killed.append):
            with self.assertRaises(subprocess.TimeoutExpired):
                update_runner.run_installer(Path("inst"), self.studio, self.data / "log.txt", COMMIT)
        self.assertEqual(len(killed), 1)


if __name__ == "__main__":
    unittest.main()
