"""KI-Motoren des Studios: Claude Code und OpenAI Codex.

Jeder Motor weiß, wie er gestartet wird, wie seine JSON-Ereignisse in Gesprächseinträge
übersetzt werden und wie Anmeldung und Anmeldestatus funktionieren.
"""

import json
import re
from pathlib import Path

import platform_support as ps

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
CLAUDE_TOOLS = ("Bash", "PowerShell", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "TodoWrite")
SHELL_NAMES = ("powershell", "pwsh", "bash", "sh", "zsh", "cmd")
SHELL_WRAPPER = re.compile(r'^\s*("[^"]*"|\S+)\s+(?:-NoProfile\s+)?(?:-Command|-lc|-c|/c)\s+(.+)$',
                           re.DOTALL | re.IGNORECASE)
FILE_VERBS = {"add": "Erstellt ", "update": "Bearbeitet ", "delete": "Löscht "}
SESSION_ID_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z_-]{7,63}")

APP_SYSTEM_PROMPT = (
    "Du arbeitest im Motion Studio, einer grafischen Oberfläche. Die Person sieht keine Konsole, "
    "nur deine Textantworten und die Videos im Ordner exports. Antworte auf Deutsch, kurz und ohne "
    "Fachjargon. Brauchst du eine Entscheidung oder Freigabe, stelle die Frage am Ende deiner "
    "Antwort und warte auf die nächste Nachricht. Nenne fertige Videos immer mit ihrem Dateinamen. "
    "Rendere bei neuen Videos und bei Änderungen immer nur eine Vorschau in niedriger Auflösung "
    "(halbe Breite und Höhe, z. B. 960 × 540 statt 1920 × 1080) und speichere sie mit der Endung "
    "_vorschau.mp4. Erstelle die finale Version in voller Auflösung nur, wenn die Person ausdrücklich "
    "darum bittet, und biete sie am Ende deiner Antwort an."
)


def conversation_instructions(folder):
    """Hinweis für die KI, wo die Dateien dieses Gesprächs hingehören."""
    if not folder:
        return ""
    return (
        "Dieses Gespräch hat einen eigenen Ordner. Speichere alle Videos, Vorschaubilder und "
        "Kontaktübersichten nur in exports/{0}/ und alle Quelldateien wie HTML und Skripte in "
        "projekte/{0}/. Andere Unterordner gehören zu anderen Gesprächen: Lies oder ändere sie nur, "
        "wenn die Person ausdrücklich darum bittet."
    ).format(folder)


def system_prompt(folder):
    extra = conversation_instructions(folder)
    return APP_SYSTEM_PROMPT + ("\n\n" + extra if extra else "")


class RunState:
    """Sammelt, was ein Motor während eines Auftrags meldet."""

    def __init__(self, add):
        self.add = add
        self.session_id = None
        self.success = False
        self.cost = None
        self.error_text = None
        self.seen = set()


def valid_session_id(value):
    """Sitzungskennungen landen als Argument im Aufruf – nur harmlose Zeichen zulassen."""
    return isinstance(value, str) and bool(SESSION_ID_PATTERN.fullmatch(value))


def short_command(command):
    first_line = command.splitlines()[0][:90] if command.strip() else "Befehl"
    return "Führt aus: " + first_line


def describe_tool(name, tool_input):
    """Übersetzt einen Claude-Werkzeugaufruf in eine verständliche Zeile."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    filename = Path(path).name if path else ""
    if name == "Write":
        return "Erstellt " + filename, path
    if name in ("Edit", "MultiEdit"):
        return "Bearbeitet " + filename, path
    if name == "Read":
        verb = "Prüft Bild " if filename.lower().endswith(IMAGE_SUFFIXES) else "Liest "
        return verb + filename, path
    if name in ("Bash", "PowerShell"):
        command = str(tool_input.get("command", ""))
        description = tool_input.get("description")
        return ("Führt aus: " + description) if description else short_command(command), command
    if name in ("Glob", "Grep"):
        return "Sucht im Projekt", str(tool_input.get("pattern", ""))
    if name == "TodoWrite":
        return "Plant die Arbeitsschritte", ""
    return "Arbeitsschritt: " + name, ""


def unwrap_shell(command):
    """Entfernt den Shell-Aufruf, den Codex um jeden Befehl legt (powershell -Command "…", bash -lc '…')."""
    match = SHELL_WRAPPER.match(command)
    if not match or not any(name in match.group(1).lower() for name in SHELL_NAMES):
        return command
    inner = match.group(2).strip()
    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "\"'":
        inner = inner[1:-1]
    return inner


def describe_codex_item(item):
    """Übersetzt einen Codex-Arbeitsschritt in eine verständliche Zeile (oder None)."""
    kind = item.get("type")
    if kind == "command_execution":
        command = unwrap_shell(str(item.get("command", "")))
        return short_command(command), command
    if kind == "file_change":
        changes = [c for c in item.get("changes") or [] if isinstance(c, dict)]
        if not changes:
            return None
        first = changes[0]
        label = FILE_VERBS.get(first.get("kind"), "Bearbeitet ") + Path(str(first.get("path", ""))).name
        if len(changes) > 1:
            label += " (+{} weitere)".format(len(changes) - 1)
        return label, "\n".join(str(c.get("path", "")) for c in changes)
    if kind == "web_search":
        return "Sucht im Web: " + str(item.get("query", ""))[:90], ""
    if kind == "todo_list":
        return "Plant die Arbeitsschritte", ""
    if kind == "mcp_tool_call":
        return "Arbeitsschritt: " + str(item.get("tool", "")), ""
    return None


class ClaudeEngine:
    key = "claude"
    label = "Claude"

    def command(self):
        return ps.claude_command()

    def chat_args(self, model, session_id, folder=None):
        args = [
            "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--permission-mode", "acceptEdits",
            "--append-system-prompt", system_prompt(folder),
        ]
        if session_id:
            args += ["--resume", session_id]
        return args + ["--allowedTools"] + list(CLAUDE_TOOLS)

    def consume(self, event, run):
        if valid_session_id(event.get("session_id")):
            run.session_id = event["session_id"]
        if event.get("type") == "result":
            run.success = not event.get("is_error") and event.get("subtype", "success") == "success"
            run.cost = event.get("total_cost_usd")
            run.error_text = None if run.success else event.get("result")
            return
        if event.get("type") != "assistant":
            return
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                run.add({"kind": "assistant", "text": block["text"]})
            elif block.get("type") == "tool_use":
                label, detail = describe_tool(block.get("name", ""), block.get("input"))
                run.add({"kind": "tool", "text": label, "detail": detail})

    def auth_args(self):
        return ["auth", "status", "--json"]

    @staticmethod
    def parse_auth(return_code, stdout, stderr):
        try:
            data = json.loads(stdout or "{}")
        except ValueError:
            return False
        return isinstance(data, dict) and bool(data.get("loggedIn"))

    def login_args(self):
        return ["auth", "login"]


class CodexEngine:
    key = "codex"
    label = "Codex"

    def command(self):
        return ps.codex_command()

    def chat_args(self, model, session_id, folder=None):
        # Volle Benutzerrechte wie bei Claude (acceptEdits + Bash): Die Codex-Sandbox kann unter Windows
        # nicht zuverlässig rendern. Dafür bekommt Codex wie Claude keine Websuche, keine Apps und keine
        # MCP-Server – fremde Webinhalte sollen nicht ungefragt Befehle mit Benutzerrechten auslösen.
        # --ignore-user-config hält persönliche Codex-Einstellungen heraus; die Regeln des Studios
        # kommen aus der CLAUDE.md im Studio-Ordner.
        args = ["exec"] + (["resume"] if session_id else []) + [
            "--json", "--skip-git-repo-check", "--ignore-user-config",
            "--dangerously-bypass-approvals-and-sandbox", "-m", model,
            "-c", 'web_search="disabled"', "-c", "features.apps=false", "-c", "mcp_servers={}",
            "-c", 'project_doc_fallback_filenames=["CLAUDE.md"]',
            "-c", "developer_instructions=" + json.dumps(system_prompt(folder)),
        ]
        if session_id:
            args.append(session_id)
        return args + ["-"]

    def consume(self, event, run):
        kind = event.get("type")
        if kind == "thread.started" and valid_session_id(event.get("thread_id")):
            run.session_id = event["thread_id"]
        elif kind == "turn.completed":
            run.success = True
        elif kind == "turn.failed":
            run.error_text = str((event.get("error") or {}).get("message") or "")
        elif kind == "error":
            run.error_text = str(event.get("message") or "")
        elif kind in ("item.started", "item.completed"):
            self._consume_item(kind, event.get("item") or {}, run)

    @staticmethod
    def _consume_item(kind, item, run):
        if item.get("type") == "agent_message":
            if kind == "item.completed" and str(item.get("text", "")).strip():
                run.add({"kind": "assistant", "text": item["text"]})
            return
        # Arbeitsschritte erscheinen sofort beim Start – und nur einmal.
        if item.get("id") in run.seen:
            return
        description = describe_codex_item(item)
        if description:
            run.seen.add(item.get("id"))
            run.add({"kind": "tool", "text": description[0], "detail": description[1]})

    def auth_args(self):
        return ["login", "status"]

    @staticmethod
    def parse_auth(return_code, stdout, stderr):
        text = ((stdout or "") + (stderr or "")).lower()
        return return_code == 0 and "logged in" in text and "not logged in" not in text

    def login_args(self):
        return ["login"]


ENGINES = {engine.key: engine for engine in (ClaudeEngine(), CodexEngine())}

# Auswahl in der Oberfläche → (Motor, Modell des Motors). Der erste Eintrag ist der Standard.
MODEL_CHOICES = {
    "opus": ("claude", "opus"),
    "sonnet": ("claude", "sonnet"),
    "codex": ("codex", "gpt-6.1-sol"),
    "codex-max": ("codex", "gpt-6-astra"),
}


def resolve_model(choice):
    engine_key, model = MODEL_CHOICES.get(choice) or next(iter(MODEL_CHOICES.values()))
    return ENGINES[engine_key], model


def engine_for(key):
    """Motor zum Schlüssel; unbekannte Schlüssel lösen einen KeyError aus."""
    return ENGINES[key]
