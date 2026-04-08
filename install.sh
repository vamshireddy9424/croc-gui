#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
#  CrocDrop Installer
#  One command: curl -fsSL https://your-host/install.sh | bash
# ──────────────────────────────────────────────────────────────────────────────

set -e

INSTALL_DIR="$HOME/.local/share/crocdrop"
BIN_DIR="$HOME/.local/bin"
SCRIPT_URL="https://raw.githubusercontent.com/YOUR_USER/crocdrop/main/croc_gui.py"

# ── Colours ──
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'

echo -e "\n${CYAN}${BOLD}  🐊 CrocDrop Installer${RESET}"
echo -e "${CYAN}  ─────────────────────────────────────────${RESET}\n"

# ── Detect OS ──
OS="$(uname -s)"
case "$OS" in
  Linux*)  PLATFORM="linux"  ;;
  Darwin*) PLATFORM="macos"  ;;
  *)       echo -e "${RED}Unsupported OS: $OS${RESET}"; exit 1 ;;
esac
echo -e "  Platform : ${BOLD}$OS${RESET}"

# ── Python 3 ──
if command -v python3 &>/dev/null; then
  PY=$(command -v python3)
  echo -e "  Python   : ${GREEN}$($PY --version)${RESET}"
else
  echo -e "${RED}Python 3 is required but not found.${RESET}"
  if [ "$PLATFORM" = "linux" ]; then
    echo "  Try: sudo apt install python3"
  else
    echo "  Download: https://www.python.org/downloads/"
  fi
  exit 1
fi

# Check tkinter is available
if ! $PY -c "import tkinter" 2>/dev/null; then
  echo -e "${YELLOW}  tkinter not found — attempting install…${RESET}"
  if command -v apt-get &>/dev/null; then
    sudo apt-get install -y python3-tk
  elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3-tkinter
  elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm tk
  elif [ "$PLATFORM" = "macos" ]; then
    brew install python-tk 2>/dev/null || echo -e "${YELLOW}  Please install python-tk manually${RESET}"
  fi
fi

# ── Install croc if missing ──
if ! command -v croc &>/dev/null; then
  echo -e "\n  ${YELLOW}Installing croc…${RESET}"
  if [ "$PLATFORM" = "macos" ] && command -v brew &>/dev/null; then
    brew install croc
  else
    curl -sL https://getcroc.schollz.com | bash
  fi
  echo -e "  ${GREEN}croc installed ✓${RESET}"
else
  echo -e "  croc     : ${GREEN}$(croc --version 2>/dev/null | head -1)${RESET}"
fi

# ── Install CrocDrop GUI ──
echo -e "\n  Installing CrocDrop…"
mkdir -p "$INSTALL_DIR" "$BIN_DIR"

# Download or copy gui script
# (In real deployment, replace with curl download)
# For local use, copy the bundled script:
SCRIPT_SRC="$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")/croc_gui.py"

if [ -f "$SCRIPT_SRC" ]; then
  cp "$SCRIPT_SRC" "$INSTALL_DIR/croc_gui.py"
else
  echo -e "  Downloading GUI script…"
  curl -fsSL "$SCRIPT_URL" -o "$INSTALL_DIR/croc_gui.py"
fi

chmod +x "$INSTALL_DIR/croc_gui.py"

# ── Create launcher ──
cat > "$BIN_DIR/crocdrop" << EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/croc_gui.py" "\$@"
EOF
chmod +x "$BIN_DIR/crocdrop"

# ── PATH check ──
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo -e "\n  ${YELLOW}Adding $BIN_DIR to PATH…${RESET}"
  SHELL_RC="$HOME/.bashrc"
  [[ "$SHELL" == *"zsh"* ]] && SHELL_RC="$HOME/.zshrc"
  echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$SHELL_RC"
  export PATH="$PATH:$BIN_DIR"
fi

# ── Create .desktop entry (Linux) ──
if [ "$PLATFORM" = "linux" ]; then
  DESKTOP_DIR="$HOME/.local/share/applications"
  mkdir -p "$DESKTOP_DIR"
  cat > "$DESKTOP_DIR/crocdrop.desktop" << EOF
[Desktop Entry]
Name=CrocDrop
Comment=Peer-to-peer encrypted file transfer
Exec=$BIN_DIR/crocdrop
Icon=network-transmit-receive
Terminal=false
Type=Application
Categories=Network;FileTransfer;
EOF
fi

echo -e "\n${GREEN}${BOLD}  ✓ CrocDrop installed!${RESET}"
echo -e "\n  ${BOLD}Launching now…${RESET}"
echo -e "  (Next time just run: ${CYAN}cropdrop${RESET})\n"

# ── Launch ──
python3 "$INSTALL_DIR/croc_gui.py" &
