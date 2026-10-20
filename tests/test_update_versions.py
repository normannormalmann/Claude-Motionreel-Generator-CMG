"""Tests für .github/scripts/update_versions.py (wöchentlicher Versions-Check)."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("update_versions", ROOT / ".github" / "scripts" / "update_versions.py")
update_versions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_versions)

MANIFEST = {"cmg": "1.1.0", "codex": "0.162.1",
            "python_packages": {"playwright": "1.64.0", "pillow": "13.0.0", "numpy": "2.5.4"}}


def fake_registry(codex="0.162.1", **packages):
    versions = dict(MANIFEST["python_packages"], **packages)

    def fetch(url):
        if "registry.npmjs.org" in url:
            return {"version": codex}
        name = url.rstrip("/").split("/")[-2]
        return {"info": {"version": versions[name]}}
    return fetch


class UpdateVersionsTests(unittest.TestCase):
    def run_check(self, fetch, argv=("x",)):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "versions.json"
            path.write_text(json.dumps(MANIFEST), encoding="utf-8")
            update_versions.main(list(argv), fetch=fetch, manifest_path=path)
            return json.loads(path.read_text(encoding="utf-8"))

    def test_the_repository_manifest_is_valid(self):
        manifest = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
        update_versions.validate_manifest(manifest)

    def test_newer_versions_are_written_and_studio_version_bumped(self):
        result = self.run_check(fake_registry(codex="0.163.0", numpy="2.6.0"))
        self.assertEqual(result["codex"], "0.163.0")
        self.assertEqual(result["python_packages"]["numpy"], "2.6.0")
        self.assertEqual(result["python_packages"]["pillow"], "13.0.0")
        self.assertEqual(result["cmg"], "1.1.1")

    def test_nothing_changes_when_everything_is_current(self):
        self.assertEqual(self.run_check(fake_registry()), MANIFEST)

    def test_older_or_prerelease_versions_are_ignored(self):
        result = self.run_check(fake_registry(codex="0.200.0-beta.1", numpy="2.5.0", pillow="14.0.0rc1"))
        self.assertEqual(result, MANIFEST)

    def test_dry_run_does_not_write(self):
        self.assertEqual(self.run_check(fake_registry(codex="0.163.0"), argv=("x", "--dry-run")), MANIFEST)

    def test_summary_lists_changes(self):
        _, changes = update_versions.updated_manifest(MANIFEST, "0.163.0", MANIFEST["python_packages"])
        report = update_versions.summary(changes)
        self.assertIn("| Codex | 0.162.1 | 0.163.0 |", report)
        self.assertIn("| Motion Studio | 1.1.0 | 1.1.1 |", report)


if __name__ == "__main__":
    unittest.main()
