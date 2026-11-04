#!/bin/bash
# Run by Moonraker after you press Update on the "acepro" entry in Software Updates
# (install_script in [update_manager acepro]). It runs the installer in --auto mode:
# the config files and links are updated, your settings are kept, a backup is made first
# (undo: ./installer.sh --undo), and the Fluidd ACE panel is put back if it is missing.
# Klipper is restarted by Moonraker afterwards. Nothing happens while a print is running.
cd "$(dirname "$0")/.." || exit 1
LOGDIR="$HOME/printer_data/logs"
[ -d "$LOGDIR" ] || LOGDIR="$(pwd)"
LOG="$LOGDIR/acepro-update.log"
{ echo "=== $(date '+%F %T') post-update ==="; } >> "$LOG"
./installer.sh --update --auto < /dev/null 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
