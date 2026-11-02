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
    printf '[stepper_x]\nstep_pin: PB13\n\n[extruder]\nheater_pin: PA0\ncontrol: pid\n' > "$h/printer_data/config/printer.cfg"
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

echo "1. Klipper, fresh install"
H="$(new_home t1)"; C="$(cfg "$H")"
inst "$H" "$A_KLIPPER"
check "installer finished"                           test "$RC" -eq 0
for f in acepro.cfg acepro_setting.cfg acepro_macros.cfg acepro_printer_macros.cfg acepro_servo.cfg acepro-install.conf; do
    check "$f written"                               test -f "$C/$f"
done
check "servo pin PB14 written"                       grep -q '^pin: PB14' "$C/acepro_servo.cfg"
check "ace_count 2"                                  grep -q '^ace_count: 2' "$C/acepro_setting.cfg"
check "nozzle pin PA4"                               python3 -I "$REPO/tools/ace_cfg_tool.py" get "$C/acepro.cfg" "filament_switch_sensor filament_runout_nozzle" switch_pin
check "RDM section left out"                         grep -q '^#\[filament_switch_sensor filament_runout_rdm\]' "$C/acepro.cfg"
check "encoder section left out"                     grep -q '^#\[filament_motion_sensor ace_encoder\]' "$C/acepro.cfg"
check "positions start locked"                       grep -q '^variable_positions_confirmed: False' "$C/acepro_macros.cfg"
check "include is the first line of printer.cfg"     test "$(head -1 "$C/printer.cfg")" = "[include acepro.cfg]"
check "driver linked"                                test -L "$H/klipper/klippy/extras/ace"
check "backup manifest exists"                       test -n "$(ls "$H"/acepro-backup/*/manifest.txt 2>/dev/null)"
check "validator passes on the result"               python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile klipper
inst "$H" "" --check;  check "--check passes"        test "$RC" -eq 0

echo "2. Undo"
inst "$H" "y\n" --undo
check "undo finished"                                test "$RC" -eq 0
check "acepro.cfg removed"                           test ! -e "$C/acepro.cfg"
check "printer.cfg restored"                         test "$(head -1 "$C/printer.cfg")" = "[stepper_x]"
check "driver link removed"                          test ! -e "$H/klipper/klippy/extras/ace"

echo "3. Dry run changes nothing"
H="$(new_home t3)"; C="$(cfg "$H")"
before="$(find "$H" -type f | sort | xargs cat | md5sum)"; lsb="$(find "$H" | sort | md5sum)"
inst "$H" '1\n1\nPA4\nn\nn\nn\ny\ny\nn\nn\n' --dry-run
check "dry run finished"                             test "$RC" -eq 0
check "dry run says nothing changed"                 grep -q "Nothing was changed" <<<"$OUT"
check "no file contents changed"                     test "$(find "$H" -type f | sort | xargs cat | md5sum)" = "$before"
check "no file or link added"                        test "$(find "$H" | sort | md5sum)" = "$lsb"

echo "4. No servo, no cutter, no bucket"
H="$(new_home t4)"; C="$(cfg "$H")"
inst "$H" '1\n1\nPA4\nn\nn\nn\nn\nn\nn\nn\ny\n'
check "installer finished"                           test "$RC" -eq 0
check "no acepro_servo.cfg"                          test ! -e "$C/acepro_servo.cfg"
check "servo switched off"                           grep -q '^variable_servo_enable: False' "$C/acepro_macros.cfg"
check "cutter switched off"                          grep -q '^variable_cutter_enable: False' "$C/acepro_macros.cfg"
check "bucket switched off"                          grep -q '^variable_poop_enable: False' "$C/acepro_macros.cfg"
check "no [servo] section anywhere"                  test -z "$(grep -l '^\[servo servo_wipe\]' "$C"/*.cfg 2>/dev/null)"
check "no [force_move] added without a cutter"       test -z "$(grep -l 'force_move' "$C/printer.cfg")"
check "validator passes on the result"               python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile klipper

echo "5. RDM and encoder sensors present"
H="$(new_home t5)"; C="$(cfg "$H")"
inst "$H" '2\n1\nPA4\ny\nPC15\ny\nPF1\nn\ny\ny\nn\nn\ny\n'
check "installer finished"                           test "$RC" -eq 0
check "RDM pin PC15"                                 grep -q '^switch_pin: PC15' "$C/acepro.cfg"
check "encoder pin PF1"                              grep -q '^switch_pin: PF1' "$C/acepro.cfg"
check "RDM mapping kept"                             grep -q '^filament_runout_sensor_name_rdm:' "$C/acepro_setting.cfg"
check "validator passes (Kalico profile)"            python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile kalico

echo "6. Simple AF with its own PAUSE and hooks"
H="$(new_home t6)"; C="$(cfg "$H")"; mkdir -p "$H/pellcorp"
printf '[gcode_macro PAUSE]\nrename_existing: PAUSE_BASE\ngcode:\n  PAUSE_BASE\n\n[gcode_macro RESUME]\nrename_existing: RESUME_BASE\ngcode:\n  RESUME_BASE\n' > "$C/client.cfg"
printf '[gcode_macro _SAF_START_PRINT_END]\ngcode:\n  M117 hi\n' > "$C/my_saf_hooks.cfg"
printf '[include client.cfg]\n[include my_saf_hooks.cfg]\n' | cat - "$C/printer.cfg" > "$C/p.new" && mv "$C/p.new" "$C/printer.cfg"
cp "$C/printer.cfg" "$ROOT/t6.printer.before"
inst "$H" '3\n2\nPA4\nn\nn\ny\nPB14\ny\ny\nn\nn\ny\n'
check "installer finished"                           test "$RC" -eq 0
check "profile detected as Simple AF"                grep -q "found Simple AF" <<<"$OUT"
check "ACE PAUSE/RESUME present on every profile"    grep -q '^\[gcode_macro PAUSE\]' "$C/acepro_printer_macros.cfg"
check "hooks file NOT written (you have hooks)"      test ! -e "$C/acepro_saf_hooks.cfg"
check "hook lines to add are shown"                  grep -q "_SAF_ON_CANCEL" <<<"$OUT"
check "your hooks file untouched"                    test "$(cat "$C/my_saf_hooks.cfg")" = "$(printf '[gcode_macro _SAF_START_PRINT_END]\ngcode:\n  M117 hi')"
check "moonraker.conf not created"                   test ! -e "$C/moonraker.conf"
check "validator passes (saf)"                       python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile saf
inst "$H" "y\n" --undo; check "undo restores printer.cfg exactly" cmp -s "$C/printer.cfg" "$ROOT/t6.printer.before"

echo "7. Simple AF without hooks gets the ACE hooks file"
H="$(new_home t7)"; C="$(cfg "$H")"; mkdir -p "$H/pellcorp"
inst "$H" '3\n1\nPA4\nn\nn\ny\nPB14\ny\ny\nn\nn\ny\n'
check "installer finished"                           test "$RC" -eq 0
check "acepro_saf_hooks.cfg written"                 test -f "$C/acepro_saf_hooks.cfg"
check "validator passes (saf)"                       python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile saf

echo "8. Update keeps your settings"
H="$(new_home t8)"; C="$(cfg "$H")"
inst "$H" "$A_KLIPPER"
sed -i 's/^variable_cut_block_x: [0-9.]*/variable_cut_block_x: 77/' "$C/acepro_macros.cfg"
sed -i 's/^pin: PB14/pin: PB9/' "$C/acepro_servo.cfg"
inst "$H" 'y\n' --update
check "update finished"                              test "$RC" -eq 0
check "your cutter X kept"                           grep -q '^variable_cut_block_x: 77' "$C/acepro_macros.cfg"
check "your servo pin kept"                          grep -q '^pin: PB9' "$C/acepro_servo.cfg"
check "RDM stays left out"                           grep -q '^#\[filament_switch_sensor filament_runout_rdm\]' "$C/acepro.cfg"
check "positions lock not re-applied on update"      grep -q '^variable_positions_confirmed: False' "$C/acepro_macros.cfg"

echo "9. Update from the OLD single-file layout (before the profiles)"
H="$(new_home t9)"; C="$(cfg "$H")"
for f in acepro.cfg acepro_setting.cfg acepro_macros.cfg acepro_printer_macros.cfg; do
    git -C "$REPO" show "backup/before-installer-v1:config/$f" > "$C/$f" 2>/dev/null || git -C "$REPO" show "465ed7b:config/$f" > "$C/$f" 2>/dev/null
done
printf '[include acepro.cfg]\n\n' | cat - "$C/printer.cfg" > "$C/p.new" && mv "$C/p.new" "$C/printer.cfg"
if grep -q '^\[servo servo_wipe\]' "$C/acepro_macros.cfg" && grep -q '^\[gcode_macro PAUSE\]' "$C/acepro_printer_macros.cfg"; then
    inst "$H" '1\ny\n' --update
    check "update finished"                          test "$RC" -eq 0
    check "servo moved into acepro_servo.cfg"        grep -q '^pin: PB14' "$C/acepro_servo.cfg"
    check "servo removed from acepro_macros.cfg"     test -z "$(grep '^\[servo servo_wipe\]' "$C/acepro_macros.cfg")"
    check "PAUSE still in acepro_printer_macros.cfg" grep -q '^\[gcode_macro PAUSE\]' "$C/acepro_printer_macros.cfg"
    check "validator passes on the result"          python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile klipper
else
    echo "  skip  old layout not available in this clone"
fi

echo "10. Repair"
H="$(new_home t10)"; C="$(cfg "$H")"
inst "$H" "$A_KLIPPER"
rm -f "$H/klipper/klippy/extras/ace"; ln -s /tmp/old "$H/klipper/klippy/extras/ace_backup_20260101_000000"
inst "$H" 'y\n' --repair
check "driver link restored"                         test -L "$H/klipper/klippy/extras/ace" -a -e "$H/klipper/klippy/extras/ace"
check "stale ace_backup link removed"                test ! -e "$H/klipper/klippy/extras/ace_backup_20260101_000000" -a ! -L "$H/klipper/klippy/extras/ace_backup_20260101_000000"

echo "11. Bad input"
H="$(new_home t11)"
inst "$H" '1\n1\nnot a pin\nx y\n!!\n@@\n##\n'
check "stops with a clear message"                   grep -q "no valid pin" <<<"$OUT"
check "changed nothing"                              test ! -e "$(cfg "$H")/acepro.cfg"

echo "12. Support bundle hides secrets"
H="$(new_home t12)"; C="$(cfg "$H")"
inst "$H" "$A_KLIPPER"
printf '\n[mqtt]\napi_key: SUPERSECRET123\n' >> "$C/printer.cfg"
inst "$H" "" --support-bundle
B="$(ls "$H"/acepro-support-*.tar.gz 2>/dev/null | head -1)"
check "bundle created"                               test -n "$B"
check "secret removed from the bundle"               test -z "$(tar -xzOf "$B" 2>/dev/null | grep SUPERSECRET123)"

echo
echo "Passed: $PASS   Failed: $FAIL"
[ "$FAIL" -eq 0 ]
