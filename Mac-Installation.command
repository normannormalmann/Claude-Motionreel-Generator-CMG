#!/bin/bash
# Doppelklick-Start für macOS: führt den Installer im Terminal aus.
cd "$(dirname "$0")" || exit 1
bash ./install.sh
echo
read -r -p "Drücke Enter, um dieses Fenster zu schließen. " _
