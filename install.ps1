# CrocDrop Windows Installer
# Run with: irm https://raw.githubusercontent.com/vamshireddy9424/croc-gui/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$INSTALL_DIR = "$env:APPDATA\CrocDrop"
$GUI_SCRIPT  = "$INSTALL_DIR\croc_gui.py"

Write-Host ""
Write-Host "  🐊 CrocDrop Installer" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────────────────" -ForegroundColor Cyan
Write-Host ""

# ── Python ──
$py = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") { $py = $cmd; break }
    } catch {}
}
if (-not $py) {
    Write-Host "  Python 3 is required. Download: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "  Python: $(& $py --version)" -ForegroundColor Green

# ── croc ──
if (-not (Get-Command croc -ErrorAction SilentlyContinue)) {
    Write-Host "  Installing croc..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install schollz.croc -e --silent
    } elseif (Get-Command scoop -ErrorAction SilentlyContinue) {
        scoop install croc
    } else {
        Write-Host "  Please install croc from: https://github.com/schollz/croc/releases" -ForegroundColor Red
        exit 1
    }
    Write-Host "  croc installed ✓" -ForegroundColor Green
} else {
    $crocVer = & croc --version 2>&1 | Select-Object -First 1
    Write-Host "  croc: $crocVer" -ForegroundColor Green
}

# ── Install GUI ──
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null

# In production, download from your server:
# Invoke-WebRequest -Uri "https://raw.githubusercontent.com/vamshireddy9424/croc-gui/main/croc_gui.py" -OutFile $GUI_SCRIPT
# For local bundled install — copy from same dir as this script:
$srcScript = Join-Path (Split-Path $MyInvocation.MyCommand.Path) "croc_gui.py"
if (Test-Path $srcScript) {
    Copy-Item $srcScript $GUI_SCRIPT -Force
} else {
    # Download
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/vamshireddy9424/croc-gui/main/croc_gui.py" `
        -OutFile $GUI_SCRIPT
}

# ── Launcher batch file ──
$launcher = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\CrocDrop.lnk"
$wshell = New-Object -ComObject WScript.Shell
$shortcut = $wshell.CreateShortcut($launcher)
$shortcut.TargetPath = "pythonw"
$shortcut.Arguments  = "`"$GUI_SCRIPT`""
$shortcut.WorkingDirectory = $INSTALL_DIR
$shortcut.Description = "CrocDrop – peer-to-peer file transfer"
$shortcut.Save()

Write-Host ""
Write-Host "  ✓ CrocDrop installed!" -ForegroundColor Green
Write-Host ""
Write-Host "  Launching now..." -ForegroundColor White
Write-Host "  (Next time: find CrocDrop in your Start Menu)" -ForegroundColor Gray
Write-Host ""

# Launch
Start-Process $py $GUI_SCRIPT
