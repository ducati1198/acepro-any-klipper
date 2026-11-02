#!/bin/bash
# Installer tests. They run installer.sh against FAKE home folders in /tmp, answer its
# questions through stdin, and never touch your printer, services or real config.
#
#   bash tests/installer/run_tests.sh
#
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT

ok()   { PASS=$((PASS+1)); echo "  ok    $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/        /' | head -25; }
check() { # description command...
    local d="$1"; shift
    if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi
}

new_home() { # name -> path of a fake home with Klipper and a printer.cfg
    local h="$ROOT/$1"
    mkdir -p "$h/klipper/klippy/extras" "$h/printer_data/config" "$h/printer_data/logs"
    printf '[stepper_x]\nstep_pin: PB13\n\n[extruder]\nheater_pin: PA0\ncontrol: pid\n\n#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# DO NOT EDIT THIS BLOCK OR BELOW. The contents are auto-generated.\n#*#\n#*# [heater_bed]\n#*# control = pid\n' > "$h/printer_data/config/printer.cfg"
    echo "$h"
}

inst() { # home answers [args...]  -> output in $OUT, exit code in $RC
    local h="$1" answers="$2"; shift 2
    OUT="$(printf '%b' "$answers" | ACE_INSTALL_HOME="$h" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" "$@" 2>&1)"; RC=$?
}
cfg() { echo "$1/printer_data/config"; }

# Answers for a fresh install, in the order the installer asks:
#  profile, ace count, nozzle pin, RDM?, encoder?, servo?, [servo pin], cutter?, bucket?, spoolman?, cutcal?, continue?
A_KLIPPER='1\n2\nPA4\nn\nn\ny\nPB14\ny\ny\nn\nn\ny\n'
H="$(new_home t24)"; C="$(cfg "$H")"; inst "$H" "$A_KLIPPER"; inst "$H" "" --doctor; echo "$OUT" | tail -12
echo =====
sed -i '/include acepro.cfg/d' "$C/printer.cfg"; printf '[force_move]\nenable_force_move: True\n' >> "$C/printer.cfg"
inst "$H" 'y\ny\n' --doctor; echo "$OUT" | tail -20; tail -12 "$C/printer.cfg"
echo =====
H="$(new_home t23)"; C="$(cfg "$H")"; inst "$H" "$A_KLIPPER"; python3 -I tools/ace_cfg_tool.py set "$C/acepro_macros.cfg" "gcode_macro _ACE_VARS" variable_cut_speed 777; inst "$H" 'y\n' --uninstall; ls $H/acepro-backup/*/files$C; ls $H
