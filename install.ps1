# Claude Motionreel Generator (CMG) - Installer für Windows.
#
# Richtet Claude Code, Git, Node.js, Python, Playwright (Chromium), FFmpeg und
# den Studio-Ordner ein. Kann beliebig oft ausgeführt werden: Bereits
# Vorhandenes wird erkannt und übersprungen.
#
# Optionale Umgebungsvariablen:
#   CMG_STUDIO_DIR      Zielordner (Standard: %USERPROFILE%\Projects\motion-studio)
#   CMG_NONINTERACTIVE  1 = keine Rückfragen (z. B. für automatische Tests)
#Requires -Version 5.1

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$RepoRaw = 'https://raw.githubusercontent.com/normannormalmann/Claude-Motionreel-Generator-CMG/main'
$FfmpegZipUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$StudioDir = if ($env:CMG_STUDIO_DIR) { $env:CMG_STUDIO_DIR } else { Join-Path $env:USERPROFILE 'Projects\motion-studio' }
$NonInteractive = $env:CMG_NONINTERACTIVE -eq '1'
$MinPythonMinor = 9
$PythonPackages = @('playwright', 'pillow', 'numpy')
$LogFile = if ($env:CMG_LOG_FILE) { $env:CMG_LOG_FILE } else { Join-Path $env:TEMP 'cmg-install.log' }
$ScriptDir = $PSScriptRoot
$VenvPython = Join-Path $StudioDir '.venv\Scripts\python.exe'
$HasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)

# ---------------------------------------------------------------- Hilfen

function Write-Step([string]$Text) { Write-Host ''; Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text)   { Write-Host "  [OK] $Text" -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host "  [!] $Text" -ForegroundColor Yellow }

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Übernimmt PATH-Änderungen von Installationen in die laufende Sitzung.
function Update-SessionPath {
    $parts = @(
        [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        $env:Path
    ) -join ';'
    $unique = $parts.Split(';') | Where-Object { $_ } | Select-Object -Unique
    $env:Path = $unique -join ';'
}

function Add-UserPath([string]$Directory) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = if ($userPath) { $userPath.Split(';') } else { @() }
    if ($entries -notcontains $Directory) {
        $newPath = (@($entries | Where-Object { $_ }) + $Directory) -join ';'
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    }
    Update-SessionPath
}

# Führt ein externes Programm aus und bricht bei einem Fehlercode ab.
function Invoke-Native([string]$Exe, [string[]]$Arguments, [string]$ErrorText) {
    $env:PYTHONIOENCODING = 'utf-8'
    & $Exe @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$ErrorText (Fehlercode $LASTEXITCODE)" }
}

function Install-WingetPackage([string]$Id, [string]$DisplayName) {
    if (-not $HasWinget) { return }
    Write-Step "Installiere $DisplayName (Windows fragt eventuell nach - bitte mit 'Ja' bestätigen)"
    & winget install --id $Id -e --source winget --accept-source-agreements --accept-package-agreements --silent | Out-Host
    Update-SessionPath
}

function Get-PythonInfo([string]$Exe, [string[]]$PrefixArgs) {
    try {
        # Keine doppelten Anführungszeichen: Windows PowerShell 5.1 gibt sie an Programme falsch weiter.
        $code = "import sys; print('%d|%d|%s' % (sys.version_info[0], sys.version_info[1], sys.executable))"
        $output = & $Exe @PrefixArgs -c $code 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }
        $major, $minor, $path = "$output".Trim().Split('|', 3)
        if ([int]$major -eq 3 -and [int]$minor -ge $MinPythonMinor) { return $path }
    } catch { }
    return $null
}

# Sucht ein geeignetes Python (3.13 bevorzugt). Ignoriert den Microsoft-Store-Platzhalter.
function Find-Python {
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3.13') },
        @{ Exe = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'); Args = @() },
        @{ Exe = (Join-Path $env:ProgramFiles 'Python313\python.exe'); Args = @() },
        @{ Exe = 'py'; Args = @('-3') },
        @{ Exe = 'python'; Args = @() }
    )
    foreach ($candidate in $candidates) {
        $isPath = $candidate.Exe.Contains('\')
        if ($isPath -and -not (Test-Path $candidate.Exe)) { continue }
        if (-not $isPath -and -not (Test-Command $candidate.Exe)) { continue }
        $path = Get-PythonInfo $candidate.Exe $candidate.Args
        if ($path) { return $path }
    }
    return $null
}

# Kopiert eine Vorlage aus dem lokalen Repo oder lädt sie von GitHub.
function Get-Template([string]$Name, [string]$Destination) {
    if ($ScriptDir) {
        $local = Join-Path $ScriptDir "studio-vorlage\$Name"
        if (Test-Path $local) { Copy-Item -LiteralPath $local -Destination $Destination -Force; return }
    }
    Invoke-WebRequest -Uri "$RepoRaw/studio-vorlage/$Name" -OutFile $Destination -UseBasicParsing
}

# ---------------------------------------------------------------- Schritte

function Install-Git {
    if (Test-Command 'git') { Write-Ok 'Git bereits installiert'; return }
    Install-WingetPackage 'Git.Git' 'Git'
    if (Test-Command 'git') { Write-Ok 'Git installiert' }
    else { Write-Warn 'Git konnte nicht installiert werden. Claude Code funktioniert ohne Git eventuell eingeschränkt.' }
}

function Install-ClaudeCode {
    $nativeBin = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path (Join-Path $nativeBin 'claude.exe')) { Add-UserPath $nativeBin }
    if (Test-Command 'claude') { Write-Ok 'Claude Code bereits installiert'; return }

    Install-WingetPackage 'Anthropic.ClaudeCode' 'Claude Code'
    if (-not (Test-Command 'claude')) {
        Write-Step 'Installiere Claude Code über den offiziellen Installer'
        $command = 'irm https://claude.ai/install.ps1 | iex'
        Invoke-Native 'powershell.exe' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command) 'Claude Code konnte nicht installiert werden'
        if (Test-Path (Join-Path $nativeBin 'claude.exe')) { Add-UserPath $nativeBin }
        Update-SessionPath
    }
    if (-not (Test-Command 'claude')) { throw 'Claude Code konnte nicht installiert werden.' }
    Write-Ok 'Claude Code installiert'
}

function Install-NodeJs {
    if (Test-Command 'node') { Write-Ok 'Node.js bereits installiert'; return }
    Install-WingetPackage 'OpenJS.NodeJS.LTS' 'Node.js'
    if (Test-Command 'node') { Write-Ok 'Node.js installiert' }
    else { Write-Warn 'Node.js konnte nicht installiert werden (optional).' }
}

function Install-Python {
    $python = Find-Python
    if (-not $python) {
        Install-WingetPackage 'Python.Python.3.13' 'Python 3.13'
        $python = Find-Python
    }
    if (-not $python) {
        throw ('Python wurde nicht gefunden. Bitte Python 3.13 von https://www.python.org/downloads/ installieren ' +
               '(Haken bei "Add python.exe to PATH" setzen) und diesen Installer erneut starten.')
    }
    Write-Ok "Python: $python"
    return $python
}

function Install-FfmpegDirect {
    Write-Step 'Lade FFmpeg direkt herunter (ca. 100 MB)'
    $target = Join-Path $env:LOCALAPPDATA 'Programs\ffmpeg'
    $zip = Join-Path $env:TEMP 'cmg-ffmpeg.zip'
    Invoke-WebRequest -Uri $FfmpegZipUrl -OutFile $zip -UseBasicParsing
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $target -Force
    Remove-Item -LiteralPath $zip -Force
    $exe = Get-ChildItem -LiteralPath $target -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1
    if (-not $exe) { throw 'FFmpeg wurde im heruntergeladenen Archiv nicht gefunden.' }
    Add-UserPath $exe.DirectoryName
}

function Install-Ffmpeg {
    if (Test-Command 'ffmpeg') { Write-Ok 'FFmpeg bereits installiert'; return }
    Install-WingetPackage 'Gyan.FFmpeg' 'FFmpeg'
    if (-not (Test-Command 'ffmpeg')) { Install-FfmpegDirect }
    if (-not (Test-Command 'ffmpeg')) { throw 'FFmpeg konnte nicht installiert werden.' }
    Write-Ok 'FFmpeg installiert'
}

function New-StudioVenv([string]$Python) {
    if (Test-Path $VenvPython) {
        # Eine defekte Umgebung (z. B. nach Python-Update) schreibt auf stderr; das wirft in PS 5.1.
        $isHealthy = $false
        try {
            & $VenvPython -c 'import sys' 2>$null | Out-Null
            $isHealthy = $LASTEXITCODE -eq 0
        } catch { }
        if ($isHealthy) { Write-Ok 'Python-Umgebung vorhanden'; return }
        Remove-Item -LiteralPath (Join-Path $StudioDir '.venv') -Recurse -Force
    }
    Invoke-Native $Python @('-m', 'venv', (Join-Path $StudioDir '.venv')) 'Die Python-Umgebung konnte nicht erstellt werden'
    Write-Ok 'Python-Umgebung erstellt'
}

function Install-RenderTools {
    Write-Step 'Installiere die Render-Werkzeuge (Playwright, Chromium, Pillow, NumPy)'
    Invoke-Native $VenvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'pip') 'pip konnte nicht aktualisiert werden'
    Invoke-Native $VenvPython (@('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade') + $PythonPackages) 'Die Python-Pakete konnten nicht installiert werden'
    Invoke-Native $VenvPython @('-m', 'playwright', 'install', 'chromium') 'Chromium konnte nicht installiert werden'
    Write-Ok 'Render-Werkzeuge installiert'
}

function Write-StudioFiles {
    Get-Template 'BEISPIEL-PROMPTS.md' (Join-Path $StudioDir 'BEISPIEL-PROMPTS.md')
    Get-Template 'selbsttest.py' (Join-Path $StudioDir 'tools\selbsttest.py')

    $claudeMd = Join-Path $StudioDir 'CLAUDE.md'
    if (Test-Path $claudeMd) { Write-Ok 'CLAUDE.md vorhanden - bleibt unverändert'; return }
    $template = Join-Path $env:TEMP 'cmg-claude-template.md'
    Get-Template 'CLAUDE.md' $template
    $text = [IO.File]::ReadAllText($template, [Text.Encoding]::UTF8)
    $text = $text.Replace('{{BETRIEBSSYSTEM}}', 'Windows (nativ)')
    $text = $text.Replace('{{SHELL_HINWEIS}}', 'Verwende PowerShell-kompatible Befehle und Windows-Pfade.')
    $text = $text.Replace('{{PYTHON}}', '.venv\Scripts\python.exe')
    [IO.File]::WriteAllText($claudeMd, $text, (New-Object Text.UTF8Encoding $false))
    Remove-Item -LiteralPath $template -Force
    Write-Ok 'CLAUDE.md mit den Studio-Regeln angelegt'
}

function New-Launchers {
    $startScript = Join-Path $StudioDir 'studio-starten.ps1'
    $content = @(
        '# Startet das Motion Studio (Claude Code im Studio-Ordner).',
        '$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")',
        'Set-Location -LiteralPath $PSScriptRoot',
        'claude'
    ) -join "`r`n"
    [IO.File]::WriteAllText($startScript, $content, (New-Object Text.UTF8Encoding $false))

    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path $desktop 'Motion Studio.lnk'))
        $shortcut.TargetPath = Join-Path $PSHOME 'powershell.exe'
        $shortcut.Arguments = "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
        $shortcut.WorkingDirectory = $StudioDir
        $shortcut.Description = 'Claude Motionreel Generator starten'
        $shortcut.Save()
        Write-Ok 'Verknüpfung "Motion Studio" auf dem Desktop angelegt'
    } catch {
        Write-Warn "Desktop-Verknüpfung konnte nicht angelegt werden: $($_.Exception.Message)"
    }
}

function Initialize-Studio([string]$Python) {
    Write-Step "Richte den Studio-Ordner ein: $StudioDir"
    foreach ($folder in @('exports', 'assets', 'tools')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $StudioDir $folder) | Out-Null
    }
    New-StudioVenv $Python
    Install-RenderTools
    Write-StudioFiles
    New-Launchers
}

function Test-Installation {
    Write-Step 'Prüfe die Installation'
    Write-Ok ("Claude Code: " + ((& claude --version) | Select-Object -First 1))
    Write-Ok ("Python:      " + ((& $VenvPython --version) | Select-Object -First 1))
    Write-Ok ("FFmpeg:      " + ((& ffmpeg -version) | Select-Object -First 1))
    if (Test-Command 'node') { Write-Ok ("Node.js:     " + (& node --version)) } else { Write-Warn 'Node.js fehlt (optional)' }

    Write-Step 'Selbsttest: kurze Testanimation rendern'
    $ffmpeg = (Get-Command ffmpeg).Source
    Invoke-Native $VenvPython @((Join-Path $StudioDir 'tools\selbsttest.py'), '--ffmpeg', $ffmpeg) 'Der Selbsttest ist fehlgeschlagen'
}

function Show-NextSteps {
    Write-Host ''
    Write-Host '==> Fertig! Dein Motion Studio ist eingerichtet.' -ForegroundColor Green
    Write-Host ''
    Write-Host "Studio-Ordner:  $StudioDir"
    Write-Host "Videos landen:  $(Join-Path $StudioDir 'exports')"
    Write-Host ''
    Write-Host 'So geht es weiter:'
    Write-Host '  1. Starte das Studio: Doppelklick auf "Motion Studio" auf dem Desktop.'
    Write-Host '  2. Beim ersten Start meldest du dich bei Claude an.'
    Write-Host '  3. Tippe /model und wähle Opus (falls verfügbar).'
    Write-Host '  4. Kopiere einen Auftrag aus BEISPIEL-PROMPTS.md im Studio-Ordner.'
    Write-Host ''
}

function Start-StudioIfWanted {
    if ($NonInteractive) { return }
    $answer = Read-Host 'Möchtest du das Studio jetzt starten? [J/n]'
    if ($answer -match '^[nN]') { return }
    Set-Location -LiteralPath $StudioDir
    & claude
}

function Main {
    Write-Host 'Claude Motionreel Generator - Installation' -ForegroundColor Cyan
    Write-Host "Protokoll: $LogFile"
    if (-not $HasWinget) {
        Write-Warn 'winget ist nicht verfügbar. Fehlende Programme werden, wo möglich, direkt heruntergeladen.'
        Write-Warn 'Tipp: Installiere im Microsoft Store das Programm "App-Installer", um winget zu erhalten.'
    }

    Write-Step 'Prüfe und installiere die benötigten Programme'
    Update-SessionPath
    Install-Git
    Install-ClaudeCode
    Install-NodeJs
    $python = Install-Python
    Install-Ffmpeg

    Initialize-Studio $python
    Test-Installation
    Show-NextSteps
}

# Externe Programme (Playwright, pip, winget) geben UTF-8 aus. Ohne diese Umstellung
# liest PowerShell 5.1 sie in der alten DOS-Codepage, und Fortschrittsbalken werden zu "ÔûáÔûá".
$originalConsoleEncoding = $null
try {
    $originalConsoleEncoding = [Console]::OutputEncoding
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
} catch { }

$transcriptStarted = $false
try {
    Start-Transcript -Path $LogFile -Append | Out-Null
    $transcriptStarted = $true
} catch { }

$exitCode = 0
try {
    Main
} catch {
    Write-Host ''
    Write-Host "FEHLER: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Ein Protokoll liegt unter: $LogFile"
    $exitCode = 1
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}

if ($exitCode -eq 0) { Start-StudioIfWanted }
if ($originalConsoleEncoding) {
    try { [Console]::OutputEncoding = $originalConsoleEncoding } catch { }
}
exit $exitCode
