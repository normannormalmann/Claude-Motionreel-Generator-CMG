"""Sucht neue Versionen von Codex und den Python-Paketen und schreibt sie in versions.json.

Aufruf:  python .github/scripts/update_versions.py [--dry-run]

Ändert sich etwas, wird die Studio-Version (cmg) um eine Patch-Stufe erhöht – daran erkennt das
Studio ein Update. Die Zusammenfassung landet als Markdown in $GITHUB_STEP_SUMMARY bzw. auf stdout,
"changed=true|false" in $GITHUB_OUTPUT. Der Workflow testet die neuen Versionen, bevor er einen PR öffnet.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio-app"))

from updates import parse_version, validate_manifest  # noqa: E402

MANIFEST = ROOT / "versions.json"
NPM_URL = "https://registry.npmjs.org/{}/latest"
PYPI_URL = "https://pypi.org/pypi/{}/json"
CODEX_PACKAGE = "@openai/codex"
TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 32 * 1024 * 1024  # PyPI-Antworten großer Pakete sind einige MB groß


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Antwort zu groß: " + url)
    return json.loads(body.decode("utf-8"))


def latest_versions(manifest, fetch=fetch_json):
    """Neueste veröffentlichte Versionen (ohne Vorabversionen) für alle Bausteine aus versions.json."""
    codex = fetch(NPM_URL.format(CODEX_PACKAGE))["version"]
    packages = {name: fetch(PYPI_URL.format(name))["info"]["version"] for name in manifest["python_packages"]}
    return codex, packages


def bump_patch(version):
    parts = list(parse_version(version))
    parts[-1] += 1
    return ".".join(str(part) for part in parts)


def updated_manifest(manifest, codex, packages):
    """Neue versions.json und die Liste der Änderungen. Herabgestuft wird nie."""
    changes = []
    result = {"cmg": manifest["cmg"], "codex": manifest["codex"], "python_packages": dict(manifest["python_packages"])}
    try:
        newer_codex = parse_version(codex) > parse_version(manifest["codex"])
    except ValueError:
        newer_codex = False  # z. B. Vorabversion wie 1.0.0-beta: überspringen
    if newer_codex:
        changes.append(("Codex", manifest["codex"], codex))
        result["codex"] = codex
    for name, version in sorted(packages.items()):
        old = manifest["python_packages"][name]
        try:
            is_newer = parse_version(version) > parse_version(old)
        except ValueError:
            continue
        if is_newer:
            changes.append((name, old, version))
            result["python_packages"][name] = version
    if changes:
        result["cmg"] = bump_patch(manifest["cmg"])
        changes.insert(0, ("Motion Studio", manifest["cmg"], result["cmg"]))
    return validate_manifest(result), changes


def summary(changes):
    if not changes:
        return "Alle Bausteine sind auf dem neuesten Stand."
    lines = ["| Baustein | Bisher | Neu |", "|---|---|---|"]
    lines += ["| {} | {} | {} |".format(name, old, new) for name, old, new in changes]
    return "\n".join(lines)


def _append(variable, text):
    target = os.environ.get(variable)
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def main(argv, fetch=fetch_json, manifest_path=MANIFEST):
    manifest = validate_manifest(json.loads(Path(manifest_path).read_text(encoding="utf-8")))
    codex, packages = latest_versions(manifest, fetch)
    new_manifest, changes = updated_manifest(manifest, codex, packages)
    report = summary(changes)
    print(report)
    _append("GITHUB_STEP_SUMMARY", "## Neue Versionen\n\n" + report)
    _append("GITHUB_OUTPUT", "changed={}".format("true" if changes else "false"))
    if changes and "--dry-run" not in argv:
        Path(manifest_path).write_text(json.dumps(new_manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
