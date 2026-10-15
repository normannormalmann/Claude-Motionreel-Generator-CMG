#!/usr/bin/env bash
# Claude Motionreel Generator (CMG) – Installer für macOS und Linux.
#
# Richtet Claude Code, Python, Playwright (Chromium), FFmpeg, den
# Studio-Ordner und die Studio-App ein. Kann beliebig oft ausgeführt werden: Bereits Vorhandenes
# wird erkannt und übersprungen.
#
# Optionale Umgebungsvariablen:
#   CMG_STUDIO_DIR      Zielordner (Standard: ~/Dokumente bzw. ~/Documents/Claude-Motion-Studio)
#   CMG_NONINTERACTIVE  1 = keine Rückfragen (z. B. für automatische Tests)
set -Eeuo pipefail

REPO_RAW="https://raw.githubusercontent.com/normannormalmann/Claude-Motionreel-Generator-CMG/main"
STUDIO_DIR=""
NONINTERACTIVE="${CMG_NONINTERACTIVE:-0}"
MIN_PYTHON_MINOR=9
PREFERRED_PYTHONS=(python3.13 python3.12 python3.11 python3.10 python3)
PYTHON_PACKAGES=(playwright pillow numpy)
LOG_FILE="${CMG_LOG_FILE:-${TMPDIR:-/tmp}/cmg-install.log}"

OS_NAME=""
PKG_MANAGER=""
PYTHON=""
# Die Python-Umgebung liegt bewusst außerhalb des Studio-Ordners: Dokumente werden
# oft per iCloud synchronisiert, und Tausende kleiner Dateien würden das lahmlegen.
APP_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/claude-motion-studio"
VENV_DIR="$APP_DATA_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
APP_DIR="$APP_DATA_DIR/app"
APP_FILES=(studio_app.py claude_bridge.py platform_support.py make_icon.py static/index.html static/app.css static/app.js)

SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

# ---------------------------------------------------------------- Hilfen

step() { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$RESET"; }
ok()   { printf '%s  ✓ %s%s\n' "$GREEN" "$1" "$RESET"; }
warn() { printf '%s  ! %s%s\n' "$YELLOW" "$1" "$RESET"; }
has()  { command -v "$1" >/dev/null 2>&1; }

die() {
  printf '\n%sFEHLER: %s%s\n' "$RED" "$1" "$RESET" >&2
  printf 'Ein Protokoll liegt unter: %s\n' "$LOG_FILE" >&2
  exit 1
}

on_error() { die "Unerwarteter Fehler (Zeile $1). Bitte das Protokoll an den Support schicken."; }

is_interactive() { [ "$NONINTERACTIVE" != "1" ]; }

run_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# Hängt eine Zeile an eine Datei an, falls sie dort noch fehlt.
persist_line() {
  local file="$1" line="$2"
  touch "$file"
  if ! grep -qxF "$line" "$file"; then
    printf '\n%s\n' "$line" >>"$file"
  fi
}

python_is_suitable() {
  "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_PYTHON_MINOR) else 1)" >/dev/null 2>&1
}

find_python() {
  local candidate
  for candidate in "$@" "${PREFERRED_PYTHONS[@]}"; do
    if [ -n "$candidate" ] && has "$candidate" && python_is_suitable "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

# Kopiert eine Datei aus dem lokalen Repo oder lädt sie von GitHub.
fetch_repo_file() {
  local relative="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/$relative" ]; then
    cp "$SCRIPT_DIR/$relative" "$dest"
  else
    curl -fsSL "$REPO_RAW/$relative" -o "$dest"
  fi
}

fetch_template() { fetch_repo_file "studio-vorlage/$1" "$2"; }

# ---------------------------------------------------------------- Schritte

detect_platform() {
  case "$(uname -s)" in
    Darwin) OS_NAME="macOS" ;;
    Linux)  OS_NAME="Linux" ;;
    *)      die "Dieses Betriebssystem wird nicht unterstützt. Für Windows bitte Windows-Installation.bat verwenden." ;;
  esac
  if ! is_interactive || ! (exec </dev/tty) 2>/dev/null; then
    NONINTERACTIVE=1
  fi
  has curl || die "Das Programm 'curl' fehlt. Bitte zuerst curl installieren."
  ok "Betriebssystem: $OS_NAME"
}

# Standard-Studio-Ordner: der Dokumente-Ordner des Systems (unter deutschem Linux oft ~/Dokumente).
resolve_studio_dir() {
  if [ -n "${CMG_STUDIO_DIR:-}" ]; then
    STUDIO_DIR="$CMG_STUDIO_DIR"
    return 0
  fi
  local documents="$HOME/Documents"
  if [ "$OS_NAME" = "Linux" ] && has xdg-user-dir; then
    local xdg_documents
    xdg_documents="$(xdg-user-dir DOCUMENTS 2>/dev/null || true)"
    if [ -n "$xdg_documents" ] && [ "$xdg_documents" != "$HOME" ]; then
      documents="$xdg_documents"
    fi
  fi
  STUDIO_DIR="$documents/Claude-Motion-Studio"
}

ask_for_password_once() {
  [ "$(id -u)" -eq 0 ] && return 0
  if is_interactive; then
    warn "Gleich wirst du nach deinem Passwort gefragt."
    warn "Beim Tippen erscheinen keine Zeichen – das ist normal. Danach Enter drücken."
    sudo -v </dev/tty
  fi
}

setup_homebrew() {
  local brew_bin="" candidate
  for candidate in "$(command -v brew 2>/dev/null || true)" /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then brew_bin="$candidate"; break; fi
  done

  if [ -z "$brew_bin" ]; then
    step "Installiere Homebrew (Paketverwaltung für macOS)"
    warn "Das kann einige Minuten dauern. Eventuell fragt dein Mac nach den Entwicklerwerkzeugen – bitte bestätigen."
    local installer
    installer="$(mktemp)"
    curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"
    if is_interactive; then
      warn "Du wirst nach deinem Mac-Passwort gefragt. Beim Tippen erscheinen keine Zeichen – das ist normal."
      /bin/bash "$installer" </dev/tty
    else
      NONINTERACTIVE=1 /bin/bash "$installer" </dev/null
    fi
    rm -f "$installer"
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      if [ -x "$candidate" ]; then brew_bin="$candidate"; break; fi
    done
    [ -n "$brew_bin" ] || die "Homebrew konnte nicht installiert werden."
  fi

  eval "$("$brew_bin" shellenv)"
  persist_line "$HOME/.zprofile" "eval \"\$($brew_bin shellenv)\""
  persist_line "$HOME/.bash_profile" "eval \"\$($brew_bin shellenv)\""
  export HOMEBREW_NO_ENV_HINTS=1
  ok "Homebrew bereit"
}

brew_install() {
  local formula="$1"
  if brew list --versions "$formula" >/dev/null 2>&1; then
    ok "$formula bereits installiert"
  else
    step "Installiere $formula (kann einige Minuten dauern)"
    brew install "$formula" </dev/null
  fi
}

install_macos_packages() {
  setup_homebrew
  brew_install python@3.13
  brew_install ffmpeg
  if has node; then ok "Node.js bereits installiert"; else brew_install node; fi
  PYTHON="$(find_python "$(brew --prefix python@3.13)/bin/python3.13")" || die "Python wurde nicht gefunden."
}

detect_linux_pkg_manager() {
  local manager
  for manager in apt-get dnf pacman zypper; do
    if has "$manager"; then PKG_MANAGER="$manager"; return 0; fi
  done
  die "Keine unterstützte Paketverwaltung gefunden (apt, dnf, pacman, zypper)."
}

install_linux_packages() {
  detect_linux_pkg_manager
  step "Installiere Systempakete mit $PKG_MANAGER"
  ask_for_password_once
  case "$PKG_MANAGER" in
    apt-get)
      run_root apt-get update </dev/null
      run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        curl ca-certificates git ffmpeg python3 python3-venv python3-pip </dev/null
      if ! has node; then
        run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs npm </dev/null \
          || warn "Node.js konnte nicht installiert werden (optional)."
      fi
      ;;
    dnf)
      run_root dnf install -y curl git python3 python3-pip </dev/null
      run_root dnf install -y ffmpeg </dev/null || run_root dnf install -y ffmpeg-free </dev/null
      has node || run_root dnf install -y nodejs </dev/null || warn "Node.js konnte nicht installiert werden (optional)."
      ;;
    pacman)
      run_root pacman -Syu --needed --noconfirm curl git python ffmpeg nodejs npm </dev/null
      ;;
    zypper)
      run_root zypper --non-interactive install curl git python3 ffmpeg nodejs </dev/null \
        || warn "Nicht alle Pakete konnten installiert werden – FFmpeg benötigt unter openSUSE eventuell das Packman-Repository."
      ;;
  esac
  has ffmpeg || die "FFmpeg konnte nicht installiert werden."
  PYTHON="$(find_python)" || die "Python 3.$MIN_PYTHON_MINOR oder neuer wurde nicht gefunden."
  ok "Systempakete installiert"
}

install_claude_code() {
  export PATH="$HOME/.local/bin:$PATH"
  local path_line='export PATH="$HOME/.local/bin:$PATH"'
  local rc rc_files
  if [ "$OS_NAME" = "macOS" ]; then
    rc_files=("$HOME/.zshrc" "$HOME/.bash_profile")
  else
    rc_files=("$HOME/.bashrc" "$HOME/.profile")
    [ -f "$HOME/.zshrc" ] && rc_files+=("$HOME/.zshrc")
  fi
  for rc in "${rc_files[@]}"; do
    persist_line "$rc" "$path_line"
  done

  if has claude; then
    ok "Claude Code bereits installiert"
    return 0
  fi
  step "Installiere Claude Code"
  local installer
  installer="$(mktemp)"
  curl -fsSL https://claude.ai/install.sh -o "$installer"
  bash "$installer" </dev/null
  rm -f "$installer"
  hash -r
  has claude || die "Claude Code konnte nicht installiert werden."
  ok "Claude Code installiert"
}

create_venv() {
  if [ -x "$VENV_PYTHON" ] && "$VENV_PYTHON" -c 'import sys' >/dev/null 2>&1; then
    ok "Python-Umgebung vorhanden"
    return 0
  fi
  rm -rf "$VENV_DIR"
  mkdir -p "$(dirname "$VENV_DIR")"
  if "$PYTHON" -m venv "$VENV_DIR"; then
    ok "Python-Umgebung erstellt"
    return 0
  fi
  if [ "$PKG_MANAGER" = "apt-get" ]; then
    local minor
    minor="$("$PYTHON" -c 'import sys; print(sys.version_info[1])')"
    run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "python3.$minor-venv" </dev/null
    rm -rf "$VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR" && ok "Python-Umgebung erstellt" && return 0
  fi
  die "Die Python-Umgebung konnte nicht erstellt werden."
}

install_chromium_deps_best_effort() {
  case "$PKG_MANAGER" in
    dnf)
      run_root dnf install -y nss atk at-spi2-atk cups-libs libdrm libxkbcommon libXcomposite \
        libXdamage libXrandr mesa-libgbm pango alsa-lib </dev/null || true ;;
    pacman)
      run_root pacman -S --needed --noconfirm nss at-spi2-core libxkbcommon libxcomposite \
        libxdamage libxrandr mesa pango alsa-lib cups </dev/null || true ;;
  esac
}

install_render_tools() {
  step "Installiere die Render-Werkzeuge (Playwright, Chromium, Pillow, NumPy)"
  "$VENV_PYTHON" -m pip install --disable-pip-version-check --upgrade pip
  "$VENV_PYTHON" -m pip install --disable-pip-version-check --upgrade "${PYTHON_PACKAGES[@]}"
  if [ "$PKG_MANAGER" = "apt-get" ]; then
    "$VENV_PYTHON" -m playwright install --with-deps chromium </dev/null
  else
    install_chromium_deps_best_effort
    "$VENV_PYTHON" -m playwright install chromium </dev/null
  fi
  ok "Render-Werkzeuge installiert"
}

write_studio_files() {
  fetch_template BEISPIEL-PROMPTS.md "$STUDIO_DIR/BEISPIEL-PROMPTS.md"
  fetch_template selbsttest.py "$STUDIO_DIR/tools/selbsttest.py"

  if [ -f "$STUDIO_DIR/CLAUDE.md" ]; then
    ok "CLAUDE.md vorhanden – bleibt unverändert"
    return 0
  fi
  local template
  template="$(mktemp)"
  fetch_template CLAUDE.md "$template"
  # Ersetzung per Python statt sed: Pfade dürfen beliebige Sonderzeichen enthalten.
  "$VENV_PYTHON" - "$template" "$STUDIO_DIR/CLAUDE.md" "$OS_NAME" \
    "Verwende bash/zsh-kompatible Befehle und Pfade mit Schrägstrichen (/)." "$VENV_PYTHON" <<'PYEOF'
import sys
source, target, os_name, shell_hint, python_path = sys.argv[1:6]
with open(source, encoding="utf-8") as handle:
    text = handle.read()
for placeholder, value in (("{{BETRIEBSSYSTEM}}", os_name), ("{{SHELL_HINWEIS}}", shell_hint), ("{{PYTHON}}", python_path)):
    text = text.replace(placeholder, value)
with open(target, "w", encoding="utf-8") as handle:
    handle.write(text)
PYEOF
  rm -f "$template"
  ok "CLAUDE.md mit den Studio-Regeln angelegt"
}

install_studio_app() {
  step "Installiere die Studio-App (Oberfläche im Browser)"
  local file
  for file in "${APP_FILES[@]}"; do
    fetch_repo_file "studio-app/$file" "$APP_DIR/$file"
  done
  "$VENV_PYTHON" - "$APP_DATA_DIR/config.json" "$STUDIO_DIR" <<'PYCONF'
import json, sys
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump({"studio_dir": sys.argv[2]}, handle, ensure_ascii=False)
PYCONF
  "$VENV_PYTHON" "$APP_DIR/make_icon.py" "$APP_DIR"
  ok "Studio-App installiert"
}

# Startskript für die Studio-App (öffnet den Browser, kein Terminal nötig).
write_app_script() {
  local target="$1"
  {
    printf '#!/bin/bash\n'
    printf '# Startet die Motion-Studio-App.\n'
    printf 'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"\n'
    printf 'exec %q %q\n' "$VENV_PYTHON" "$APP_DIR/studio_app.py"
  } >"$target"
  chmod +x "$target"
}

# Für Fortgeschrittene: Claude Code direkt im Terminal.
write_terminal_script() {
  local target="$1"
  {
    printf '#!/usr/bin/env bash\n'
    printf '# Startet Claude Code im Studio-Ordner (Terminal-Modus).\n'
    printf 'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"\n'
    printf 'cd %q || exit 1\n' "$STUDIO_DIR"
    printf 'claude\n'
  } >"$target"
  chmod +x "$target"
}

create_macos_app() {
  local app="$HOME/Applications/Motion Studio.app"
  mkdir -p "$app/Contents/MacOS"
  cat >"$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>motion-studio</string>
  <key>CFBundleIdentifier</key><string>com.github.cmg.motion-studio</string>
  <key>CFBundleName</key><string>Motion Studio</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
  <key>CFBundleIconFile</key><string>icon</string>
</dict>
</plist>
PLIST
  write_app_script "$app/Contents/MacOS/motion-studio"
  mkdir -p "$app/Contents/Resources"
  sips -s format icns "$APP_DIR/icon.png" --out "$app/Contents/Resources/icon.icns" >/dev/null 2>&1 || true
  ok "„Motion Studio“ im Ordner Programme (Benutzer) angelegt"

  if [ -d "$HOME/Desktop" ]; then
    rm -f "$HOME/Desktop/Motion Studio.command" 2>/dev/null || true
    if ln -sfn "$app" "$HOME/Desktop/Motion Studio.app" 2>/dev/null; then
      ok "Startsymbol „Motion Studio“ auf dem Schreibtisch angelegt"
    else
      warn "Kein Zugriff auf den Schreibtisch – starte das Studio über Finder → Programme → Motion Studio."
    fi
  fi
}

create_linux_launchers() {
  local apps_dir="$HOME/.local/share/applications"
  local entry="$apps_dir/motion-studio.desktop"
  mkdir -p "$apps_dir"
  write_app_script "$APP_DATA_DIR/motion-studio.sh"
  cat >"$entry" <<EOF
[Desktop Entry]
Type=Application
Name=Motion Studio
Comment=Videos mit Claude erstellen
Exec="$APP_DATA_DIR/motion-studio.sh"
Terminal=false
Icon=$APP_DIR/icon.png
Categories=AudioVideo;Video;
EOF
  chmod +x "$entry"
  ok "„Motion Studio“ im Anwendungsmenü angelegt"

  local desktop_dir
  desktop_dir="$( (has xdg-user-dir && xdg-user-dir DESKTOP) || echo "$HOME/Desktop")"
  if [ -d "$desktop_dir" ]; then
    if cp "$entry" "$desktop_dir/motion-studio.desktop" && chmod +x "$desktop_dir/motion-studio.desktop"; then
      if has gio; then gio set "$desktop_dir/motion-studio.desktop" metadata::trusted true 2>/dev/null || true; fi
      ok "Startsymbol „Motion Studio“ auf dem Schreibtisch angelegt"
    else
      warn "Startsymbol auf dem Schreibtisch konnte nicht angelegt werden (Anwendungsmenü funktioniert)."
    fi
  fi
}

create_launchers() {
  write_terminal_script "$STUDIO_DIR/studio-im-terminal.sh"
  rm -f "$STUDIO_DIR/studio-starten.sh"
  if [ "$OS_NAME" = "macOS" ]; then create_macos_app; else create_linux_launchers; fi
}

setup_studio() {
  step "Richte den Studio-Ordner ein: $STUDIO_DIR"
  if ! mkdir -p "$STUDIO_DIR/exports" "$STUDIO_DIR/assets" "$STUDIO_DIR/tools"; then
    if [ "$OS_NAME" = "macOS" ]; then
      warn "Das Terminal braucht Zugriff auf deinen Ordner „Dokumente“."
      warn "Systemeinstellungen → Datenschutz & Sicherheit → Dateien und Ordner → Terminal → „Dokumente“ einschalten."
    fi
    die "Der Studio-Ordner konnte nicht angelegt werden: $STUDIO_DIR"
  fi
  create_venv
  install_render_tools
  write_studio_files
  install_studio_app
  create_launchers
}

verify_installation() {
  step "Prüfe die Installation"
  ok "Claude Code: $(claude --version 2>/dev/null | head -n 1)"
  ok "Python:      $("$VENV_PYTHON" --version 2>&1)"
  ok "FFmpeg:      $(ffmpeg -version 2>/dev/null | head -n 1 | cut -d' ' -f1-3)"
  if has node; then ok "Node.js:     $(node --version)"; else warn "Node.js fehlt (optional)"; fi

  "$VENV_PYTHON" -c 'import sys; sys.path.insert(0, sys.argv[1]); import studio_app' "$APP_DIR"     || die "Die Studio-App lässt sich nicht laden."
  ok "Studio-App:  bereit"

  step "Selbsttest: kurze Testanimation rendern"
  if "$VENV_PYTHON" "$STUDIO_DIR/tools/selbsttest.py" --ffmpeg "$(command -v ffmpeg)"; then
    return 0
  fi
  if [ "$PKG_MANAGER" = "dnf" ]; then
    warn "Fedora-Hinweis: Das vorinstallierte ffmpeg-free kann kein H.264."
    warn "Aktiviere RPM Fusion (https://rpmfusion.org/Configuration) und führe dann aus:"
    warn "  sudo dnf install ffmpeg --allowerasing"
    warn "Danach diesen Installer erneut starten."
  fi
  die "Der Selbsttest ist fehlgeschlagen."
}

print_next_steps() {
  printf '\n%s%s==> Fertig! Dein Motion Studio ist eingerichtet.%s\n\n' "$BOLD" "$GREEN" "$RESET"
  printf 'Studio-Ordner:  %s\n' "$STUDIO_DIR"
  printf 'Videos landen:  %s/exports\n\n' "$STUDIO_DIR"
  printf 'So geht es weiter:\n'
  printf '  1. Doppelklick auf „Motion Studio“ auf dem Schreibtisch. Das Studio öffnet sich im Browser.\n'
  printf '  2. Beim ersten Start meldest du dich dort bei Claude an.\n'
  printf '  3. Wähle eine Vorlage oder beschreibe dein Video und klicke auf „Senden“.\n\n'
}

offer_to_start() {
  is_interactive || return 0
  local answer=""
  read -r -p "Möchtest du das Studio jetzt öffnen? [J/n] " answer </dev/tty || true
  case "$answer" in
    [nN]*) return 0 ;;
  esac
  nohup "$VENV_PYTHON" "$APP_DIR/studio_app.py" >/dev/null 2>&1 &
  disown || true
  ok "Das Studio öffnet sich in deinem Browser."
}

main() {
  exec 3>&1 4>&2
  exec > >(tee -a "$LOG_FILE") 2>&1
  trap 'on_error $LINENO' ERR

  printf '%sClaude Motionreel Generator – Installation%s\n' "$BOLD" "$RESET"
  printf 'Protokoll: %s\n' "$LOG_FILE"

  step "Prüfe das System"
  detect_platform
  resolve_studio_dir
  if [ "$OS_NAME" = "macOS" ]; then install_macos_packages; else install_linux_packages; fi
  ok "Python: $PYTHON"
  install_claude_code
  setup_studio
  verify_installation
  print_next_steps
  offer_to_start
}

# Der Aufruf steht bewusst am Ende: So ist das Skript bei "curl | bash"
# vollständig geladen, bevor etwas ausgeführt wird.
main "$@"
