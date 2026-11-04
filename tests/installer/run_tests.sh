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
check "force_move is above the SAVE_CONFIG block"    test "$(grep -n '^\[force_move\]' "$C/printer.cfg" | cut -d: -f1)" -lt "$(grep -n 'SAVE_CONFIG' "$C/printer.cfg" | cut -d: -f1)"
check "nothing but #*# lines below SAVE_CONFIG"      test -z "$(sed -n '/SAVE_CONFIG/,$p' "$C/printer.cfg" | grep -v '^#\*#' | grep -v '^$')"
check "saved block still ends with heater_bed value" test "$(tail -1 "$C/printer.cfg")" = "#*# control = pid"
printf '[force_move]\nenable_force_move: True\n' >> "$C/printer.cfg"
check "validator catches lines below SAVE_CONFIG"    bash -c '! python3 -I "$0/tools/validate_config.py" "$1/printer.cfg" >/dev/null' "$REPO" "$C"
head -n -2 "$C/printer.cfg" > "$C/p.tmp" && mv "$C/p.tmp" "$C/printer.cfg"
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
check "your hooks file kept your line"              grep -q 'M117 hi' "$C/my_saf_hooks.cfg"
check "ACE pause/resume hooks added to it"           bash -c 'grep -q _ACE_ON_PAUSE "$0" && grep -q _ACE_ON_RESUME "$0"' "$C/my_saf_hooks.cfg"
check "no encoder lines (no encoder chosen)"         test -z "$(grep SFS_ "$C/my_saf_hooks.cfg")"
check "include not added twice"                      test "$(grep -c 'include my_saf_hooks.cfg' "$C/printer.cfg")" -eq 1
check "no separate acepro_saf_hooks.cfg"             test ! -e "$C/acepro_saf_hooks.cfg"
check "moonraker.conf not created"                   test ! -e "$C/moonraker.conf"
check "validator passes (saf)"                       python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile saf
inst "$H" "y\n" --undo; check "undo restores printer.cfg exactly" cmp -s "$C/printer.cfg" "$ROOT/t6.printer.before"
check "undo restores your hooks file exactly"        test "$(cat "$C/my_saf_hooks.cfg")" = "$(printf '[gcode_macro _SAF_START_PRINT_END]\ngcode:\n  M117 hi')"

echo "7. Simple AF without a hooks file: new my_saf_hooks.cfg, include added"
H="$(new_home t7)"; C="$(cfg "$H")"; mkdir -p "$H/pellcorp"
inst "$H" '3\n1\nPA4\nn\nn\ny\nPB14\ny\ny\nn\nn\ny\ny\n'
check "installer finished"                           test "$RC" -eq 0
check "my_saf_hooks.cfg written"                     test -f "$C/my_saf_hooks.cfg"
check "include added to printer.cfg"                 grep -q '^\[include my_saf_hooks.cfg\]' "$C/printer.cfg"
check "pause/resume hooks call the ACE steps"        bash -c 'grep -q _ACE_ON_PAUSE "$0" && grep -q _ACE_ON_RESUME "$0"' "$C/my_saf_hooks.cfg"
check "no encoder lines (no encoder chosen)"         test -z "$(grep SFS_ "$C/my_saf_hooks.cfg")"
check "validator passes (saf)"                       python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile saf

echo "7b. Simple AF with encoder, your hooks file, manual include, a hook defined elsewhere"
H="$(new_home t7b)"; C="$(cfg "$H")"; mkdir -p "$H/pellcorp"
printf '[gcode_macro _SAF_START_PRINT_END]\ngcode:\n   M117 start\n   SFS_ENABLE_ACE_ENCODER\n   M117 more\n\n[gcode_macro _SAF_END_PRINT_START]\ngcode:\n   M117 end\n' > "$C/my_saf_hooks.cfg"
printf '[gcode_macro _SAF_ON_RESUME]\ngcode:\n  M117 mine\n' > "$C/my_other.cfg"
inst "$H" '3\n1\nPA4\nn\ny\nPF1\ny\nPB14\ny\ny\nn\nn\nn\ny\n'
check "installer finished"                           test "$RC" -eq 0
nth() { awk -v m="$2" -v n="$3" '$0=="[gcode_macro " m "]"{f=1;next} f&&/^gcode:/{g=1;next} g&&$1!~/^#/&&NF{c++; if(c==n){print $1; exit}}' "$1"; }
check "ZERO_OUT_SERVO first in START_PRINT_END"      test "$(nth "$C/my_saf_hooks.cfg" _SAF_START_PRINT_END 1)" = "ZERO_OUT_SERVO"
check "encoder line second (moved up)"               test "$(nth "$C/my_saf_hooks.cfg" _SAF_START_PRINT_END 2)" = "SFS_ENABLE_ACE_ENCODER"
check "END_PRINT_START: encoder first"               test "$(nth "$C/my_saf_hooks.cfg" _SAF_END_PRINT_START 1)" = "SFS_DISABLE_ACE_ENCODER"
check "END_PRINT_START: ZERO_OUT_SERVO NOT on top"   test "$(nth "$C/my_saf_hooks.cfg" _SAF_END_PRINT_START 1)" != "ZERO_OUT_SERVO"
check "END_PRINT_START: ZERO_OUT_SERVO added below"  test "$(nth "$C/my_saf_hooks.cfg" _SAF_END_PRINT_START 2)" = "ZERO_OUT_SERVO"
check "no ZERO_OUT_SERVO in CANCEL, NOZZLE, RUNOUT hooks" bash -c 'for m in _SAF_ON_CANCEL _SAF_HEATING_NOZZLE_START _SAF_HEATING_NOZZLE_END _SAF_ON_FILAMENT_RUNOUT; do awk -v m="$m" "\$0==\"[gcode_macro \" m \"]\"{f=1;next} /^\\[/{f=0} f&&/ZERO_OUT_SERVO/{exit 1}" "$0" || exit 1; done' "$C/my_saf_hooks.cfg"
check "ZERO_OUT_SERVO in the other hooks"            bash -c 'for m in _SAF_HOMING_START _SAF_HEATING_BED_START _SAF_BED_MESH_END _SAF_END_PRINT_END _SAF_ON_PAUSE; do awk -v m="$m" "\$0==\"[gcode_macro \" m \"]\"{f=1;next} f&&/^gcode:/{g=1;next} g&&NF{print \$1; exit}" "$0" | grep -qx ZERO_OUT_SERVO || exit 1; done' "$C/my_saf_hooks.cfg"
check "your lines kept"                              bash -c 'grep -q "M117 more" "$0" && grep -q "M117 end" "$0"' "$C/my_saf_hooks.cfg"
check "hook defined elsewhere not added"             test -z "$(grep '_SAF_ON_RESUME' "$C/my_saf_hooks.cfg")"
check "hook defined elsewhere is listed"             grep -q "_SAF_ON_RESUME" <<<"$OUT"
check "manual include: line not added"               test -z "$(grep 'include my_saf_hooks.cfg' "$C/printer.cfg")"
check "manual include: told where to add it"         grep -q "include my_saf_hooks.cfg" <<<"$OUT"

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

echo "16. One ACE temperature sensor per unit"
for n in 1 2 3; do
    H="$(new_home t16_$n)"; C="$(cfg "$H")"
    inst "$H" "1\n$n\nPA4\nn\nn\nn\ny\ny\nn\nn\ny\n"
    live="$(grep -c '^\[temperature_sensor acepro_temp_' "$C/acepro_setting.cfg")"
    check "$n unit(s): $n live temperature sensor(s)"  test "$live" -eq "$n"
    check "$n unit(s): validator passes"                python3 -I "$REPO/tools/validate_config.py" "$C/printer.cfg" --profile klipper
done

echo "17. Refuses to run while printing"
H="$(new_home t17)"
OUT="$(printf '%b' "$A_KLIPPER" | ACE_PRINT_STATE=printing ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" 2>&1)"; RC=$?
check "exits with an error"                          test "$RC" -ne 0
check "says a print is running"                      grep -q "print is printing" <<<"$OUT"
check "changed nothing"                              test ! -e "$(cfg "$H")/acepro.cfg"
OUT="$(ACE_PRINT_STATE=paused ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" --check 2>&1)"
check "--check still works while printing"           bash -c '! grep -q "a print is" <<<"$0"' "$OUT"

echo "18. ACE USB warning"
H="$(new_home t18)"
OUT="$(printf '%b' "$A_KLIPPER" | ACE_USB_LIST="nothing here" ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" 2>&1)"; RC=$?
check "warns but still installs"                     bash -c 'test "$0" -eq 0 && grep -q "do not see an ACE" <<<"$1"' "$RC" "$OUT"
H="$(new_home t18b)"
OUT="$(printf '%b' "$A_KLIPPER" | ACE_USB_LIST="Bus 001 Device 004: ID 28e9:018a ACE" ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" 2>&1)"
check "no warning when found"                        bash -c '! grep -q "do not see an ACE" <<<"$0"' "$OUT"

echo "19. Folder layouts"
H="$ROOT/t19m"; mkdir -p "$H/klipper/klippy/extras" "$H/printer_1_data/config" "$H/printer_2_data/config"
printf '[stepper_x]\nstep_pin: PB13\n' > "$H/printer_2_data/config/printer.cfg"
inst "$H" "2\n1\n2\nPA4\nn\nn\nn\ny\ny\nn\nn\ny\n"
check "multi-instance: second printer chosen"        test -f "$H/printer_2_data/config/acepro.cfg"
check "multi-instance: first printer untouched"      test ! -e "$H/printer_1_data/config/acepro.cfg"
H="$ROOT/t19k"; K="$ROOT/t19k_usr"; mkdir -p "$H" "$K/klipper/klippy/extras" "$K/printer_data/config"
printf '[stepper_x]\nstep_pin: PB13\n' > "$K/printer_data/config/printer.cfg"
OUT="$(printf '%b' "$A_KLIPPER" | ACE_K1_ROOT="$K" ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" 2>&1)"; RC=$?
check "K1 native: installed"                         test -f "$K/printer_data/config/acepro.cfg"
check "K1 native: marked experimental"               grep -q "experimental" <<<"$OUT"

echo "20. Virtual pin used before [virtual_pins]"
H="$(new_home t20)"; C="$(cfg "$H")"
printf '[output_pin foo]\npin: virtual_pin:foo\n' > "$C/early.cfg"
printf '[include early.cfg]\n' | cat - "$C/printer.cfg" > "$C/p.new" && mv "$C/p.new" "$C/printer.cfg"
printf '[virtual_pins]\n' > "$ROOT/vp_ok.cfg"
check "validator flags it"                           bash -c 'python3 -I "$0/tools/validate_config.py" "$1/printer.cfg" | grep -q "before \[virtual_pins\]"' "$REPO" "$C"
# The installer puts acepro.cfg (which loads [virtual_pins]) first, so the fresh install fixes it by itself:
inst "$H" "$A_KLIPPER"
check "after install the order is fine"              bash -c '! python3 -I "$0/tools/validate_config.py" "$1/printer.cfg" | grep -q "before \[virtual_pins\]"' "$REPO" "$C"

echo "21. Uninstall (Klipper) and undo"
H="$(new_home t21)"; C="$(cfg "$H")"
cp "$C/printer.cfg" "$ROOT/t21.orig"
inst "$H" "$A_KLIPPER"
check "installed"                                    test -f "$C/acepro.cfg"
inst "$H" "" --uninstall --dry-run
check "dry run removes nothing"                      test -f "$C/acepro.cfg"
inst "$H" 'y\n' --uninstall
check "uninstall finished"                           test "$RC" -eq 0
for f in acepro.cfg acepro_setting.cfg acepro_macros.cfg acepro_printer_macros.cfg acepro_servo.cfg acepro-install.conf; do
    check "$f removed"                               test ! -e "$C/$f"
done
check "driver link removed"                          test ! -e "$H/klipper/klippy/extras/ace" -a ! -L "$H/klipper/klippy/extras/ace"
check "include line removed"                         test -z "$(grep 'include acepro.cfg' "$C/printer.cfg")"
check "SAVE_CONFIG block untouched"                  test "$(tail -1 "$C/printer.cfg")" = "#*# control = pid"
inst "$H" 'y\n' --undo
check "undo brings the ACE files back"               test -f "$C/acepro.cfg" -a -L "$H/klipper/klippy/extras/ace"
check "undo brings the include line back"            grep -q 'include acepro.cfg' "$C/printer.cfg"
inst "$H" 'n\n' --uninstall
check "answering no changes nothing"                 test -f "$C/acepro.cfg"

echo "22. Uninstall (Simple AF): your hooks stay, ACE lines go"
H="$(new_home t22)"; C="$(cfg "$H")"; mkdir -p "$H/pellcorp"
printf '[gcode_macro _SAF_START_PRINT_END]\ngcode:\n   M117 start\n\n[gcode_macro mine]\ngcode:\n   G28\n' > "$C/my_saf_hooks.cfg"
inst "$H" '3\n1\nPA4\nn\ny\nPF1\ny\nPB14\ny\ny\nn\nn\ny\ny\n'
check "ACE line was added"                           grep -q ZERO_OUT_SERVO "$C/my_saf_hooks.cfg"
inst "$H" 'y\n' --uninstall
check "ACE lines gone"                               test -z "$(grep -E 'ZERO_OUT_SERVO|ACE_ENCODER|_ACE_ON_' "$C/my_saf_hooks.cfg")"
check "your lines kept"                              bash -c 'grep -q "M117 start" "$0" && grep -q "G28" "$0"' "$C/my_saf_hooks.cfg"
H="$(new_home t22b)"; C="$(cfg "$H")"; mkdir -p "$H/pellcorp"
inst "$H" '3\n1\nPA4\nn\ny\nPF1\ny\nPB14\ny\ny\nn\nn\ny\ny\n'
check "new hooks file written"                       test -f "$C/my_saf_hooks.cfg"
inst "$H" 'y\n' --uninstall
check "hooks file removed when only ACE lines"       test ! -e "$C/my_saf_hooks.cfg"
check "its include line removed"                     test -z "$(grep 'my_saf_hooks' "$C/printer.cfg")"

echo "23. Import values from an earlier install"
H="$(new_home t23)"; C="$(cfg "$H")"
inst "$H" "$A_KLIPPER"
python3 -I "$REPO/tools/ace_cfg_tool.py" set "$C/acepro_macros.cfg" "gcode_macro _ACE_VARS" variable_cut_speed 777
inst "$H" 'y\n' --uninstall
mkdir -p "$H/acepro-removed-1"; cp "$H"/acepro-backup/*uninstall/files"$C"/acepro_macros.cfg "$H/acepro-removed-1/" 2>/dev/null
inst "$H" "1\n2\nPA4\nn\nn\ny\nPB14\ny\ny\nn\nn\n1\ny\n"
check "import list shown"                            grep -q "Values from an earlier" <<<"$OUT"
check "your value copied"                            grep -q 'variable_cut_speed: *777' "$C/acepro_macros.cfg"
inst "$H" 'y\n' --uninstall
H2="$(new_home t23b)"; inst "$H2" "$A_KLIPPER"
check "no import question on a clean home"           bash -c '! grep -q "Values from an earlier" <<<"$0"' "$OUT"

echo "24. Doctor"
H="$(new_home t24)"; C="$(cfg "$H")"
inst "$H" "$A_KLIPPER"
inst "$H" "" --doctor
check "healthy install: no problems"                 grep -q "No problems found" <<<"$OUT"
sed -i '/include acepro.cfg/d' "$C/printer.cfg"
printf '[gcode_macro STRAY]\ngcode:\n  M117 x\n' >> "$C/printer.cfg"
cp "$C/printer.cfg" "$ROOT/t24.before"
inst "$H" 'n\nn\n' --doctor --dry-run
check "dry run changes nothing"                      cmp -s "$C/printer.cfg" "$ROOT/t24.before"
inst "$H" 'y\ny\n' --doctor
check "missing include found and offered"            grep -q "does not include acepro.cfg" <<<"$OUT"
check "below-SAVE_CONFIG found"                      grep -q "BELOW" <<<"$OUT"
check "include fixed"                                grep -q 'include acepro.cfg' "$C/printer.cfg"
check "lines moved above SAVE_CONFIG"                test "$(grep -n '^\[gcode_macro STRAY\]' "$C/printer.cfg" | cut -d: -f1)" -lt "$(grep -n 'SAVE_CONFIG' "$C/printer.cfg" | cut -d: -f1)"
check "saved block intact"                           test "$(tail -1 "$C/printer.cfg")" = "#*# control = pid"
inst "$H" "" --doctor
check "second run is clean"                          grep -q "No problems found" <<<"$OUT"
inst "$H" 'y\n' --undo

echo "25. Software Updates entry and what changed"
H="$(new_home t25)"; C="$(cfg "$H")"
printf '[server]\nhost: 0.0.0.0\n' > "$C/moonraker.conf"
inst "$H" "$A_KLIPPER"
check "update_manager entry added"                   grep -q '^\[update_manager acepro\]' "$C/moonraker.conf"
check "points at this clone"                         grep -q "^path: $REPO" "$C/moonraker.conf"
check "user's moonraker lines kept"                  grep -q '^host: 0.0.0.0' "$C/moonraker.conf"
inst "$H" 'y\n' --update
check "second run adds it only once"                 test "$(grep -c '^\[update_manager acepro\]' "$C/moonraker.conf")" -eq 1
sed -i 's/^VERSION=.*/VERSION="1.0.0"/' "$C/acepro-install.conf"
inst "$H" 'y\ny\ny\ny\n' --update
check "update lists what changed"                    grep -q "What changed since v1.0.0" <<<"$OUT"
check "lists the new version's entries"              grep -q "ACE_SELFTEST" <<<"$OUT"
inst "$H" 'y\ny\ny\ny\n' --update
check "same version: nothing new"                    grep -q "Nothing new since your last install" <<<"$OUT"
# saved answers must describe what is installed, not the defaults (servo was saved as "0" before)
[ -f "$C/acepro_servo.cfg" ] || printf '[servo servo_wipe]\npin: PB14\n' > "$C/acepro_servo.cfg"
sed -i 's/^HAVE_SERVO=.*/HAVE_SERVO="0"/' "$C/acepro-install.conf"
inst "$H" 'y\ny\ny\ny\n' --update
check "update saves HAVE_SERVO=1 when a servo is installed" grep -q '^HAVE_SERVO="1"' "$C/acepro-install.conf"
check "update saves the cutter answer"               grep -q '^HAVE_CUTTER="1"' "$C/acepro-install.conf"
inst "$H" 'y\n' --uninstall
check "uninstall removes the entry"                  test -z "$(grep 'update_manager acepro' "$C/moonraker.conf")"
check "uninstall keeps your moonraker lines"         grep -q '^host: 0.0.0.0' "$C/moonraker.conf"
H="$(new_home t25s)"; C="$(cfg "$H")"; mkdir -p "$H/pellcorp"
printf '[server]\nhost: 0.0.0.0\n' > "$C/moonraker.conf"
inst "$H" '3\n1\nPA4\nn\ny\nPF1\ny\nPB14\ny\ny\nn\nn\ny\ny\nn\n'
check "Simple AF: asked first, said no, nothing added" test -z "$(grep 'update_manager acepro' "$C/moonraker.conf")"

echo "26. Fluidd macro category"
H="$(new_home t26)"; C="$(cfg "$H")"
printf '{"categories":[{"id":"c1","name":"FILAMENT"}],"stored":[{"alias":"","visible":true,"disabledWhilePrinting":false,"color":"#ff7c00","categoryId":"c1","name":"LOAD_FILAMENT"}],"expanded":[]}' > "$ROOT/db26.json"
cp "$ROOT/db26.json" "$ROOT/db26.orig"
python3 "$REPO/tests/installer/fake_moonraker.py" "$ROOT/db26.json" "$ROOT/port26" & FAKE=$!
for i in 1 2 3 4 5 6 7 8 9 10; do [ -s "$ROOT/port26" ] && break; sleep 0.3; done
MURL="http://127.0.0.1:$(cat "$ROOT/port26")"
OUT="$(printf '%b' "$A_KLIPPER" | ACE_MOONRAKER_URL="$MURL" ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" 2>&1)"; RC=$?
check "installer finished"                           test "$RC" -eq 0
check "category created"                             grep -q '"ACEPRO MACRO"' "$ROOT/db26.json"
check "CUT_TIP is in it, pink"                       python3 -c "import json,sys; d=json.load(open(sys.argv[1])); c=[x['id'] for x in d['categories'] if x['name']=='ACEPRO MACRO'][0]; m={x['name']:x for x in d['stored']}; sys.exit(0 if m['CUT_TIP']['categoryId']==c and m['CUT_TIP']['color']=='#ff00aa' else 1)" "$ROOT/db26.json"
check "underscore macros not added"                  bash -c '! grep -q "\"_ACE_VARS\"" "$0"' "$ROOT/db26.json"
check "your categorised macro untouched"             grep -q '"categoryId": *"c1"' "$ROOT/db26.json"
OUT="$(printf 'y\n' | ACE_MOONRAKER_URL="$MURL" ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" --uninstall 2>&1)"
check "uninstall removes the category"               bash -c '! grep -q "ACEPRO MACRO" "$0"' "$ROOT/db26.json"
OUT="$(printf 'y\n' | ACE_MOONRAKER_URL="$MURL" ACE_INSTALL_HOME="$H" ACE_INSTALLER_TEST=1 bash "$REPO/installer.sh" --undo 2>&1)"
check "undo puts the category back"                  grep -q '"ACEPRO MACRO"' "$ROOT/db26.json"
kill $FAKE 2>/dev/null; wait $FAKE 2>/dev/null
H="$(new_home t26b)"
inst "$H" "$A_KLIPPER"
check "no Moonraker in test mode: installs fine"     test "$RC" -eq 0

echo
echo "14. [force_move] already in another file is not added twice"
H="$(new_home t14)"; C="$(cfg "$H")"
printf '[force_move]\nenable_force_move: true\n' > "$C/homing.cfg"; printf '[include homing.cfg]\n' | cat - "$C/printer.cfg" > "$C/p.new" && mv "$C/p.new" "$C/printer.cfg"
inst "$H" "$A_KLIPPER"
check "installer finished"                           test "$RC" -eq 0
check "no second [force_move] in printer.cfg"        test -z "$(grep '^\[force_move\]' "$C/printer.cfg")"
echo "15. Validator: inline comments inside a template are not errors"
printf '[gcode_macro T]\ngcode:\n  {%% set a = 1 if x == ""   # why\n        else 2 %%}\n  M117 {a}\n' > "$ROOT/t15.cfg"
check "no template error"                            bash -c 'python3 -I "$0/tools/validate_config.py" "$1" --profile klipper | grep -q "template error" && exit 1 || exit 0' "$REPO" "$ROOT/t15.cfg"

echo "16. Validator: a broken symlink include is an error, not a crash"
mkdir -p "$ROOT/t16"; printf '[include broken.cfg]\n' > "$ROOT/t16/printer.cfg"; ln -sf /nonexistent/x "$ROOT/t16/broken.cfg"
check "reports it as an error, no traceback"         bash -c 'out="$(python3 -I "$0/tools/validate_config.py" "$1" 2>&1)"; echo "$out" | grep -q "cannot be read" && ! echo "$out" | grep -q Traceback' "$REPO" "$ROOT/t16/printer.cfg"

echo "17. Resume: the retract after the wipe is there, the old pre-wipe variable is gone"
check "resume retracts after the wipe (hook)"        bash -c 'sed -n "/gcode_macro _ACE_ON_RESUME/,\$p" "$0/config/acepro_printer_macros.cfg" | grep -q "G1 E-{post_wipe_retract + unretract}"' "$REPO"
check "resume retracts after the wipe (RESUME)"      grep -q "G1 E-{post_wipe_retract} F1800" "$REPO/config/acepro_printer_macros.cfg"
check "no pre_wipe_retract left"                     bash -c '! grep -rq pre_wipe_retract "$0/config" "$0/variants"' "$REPO"
check "new resume settings exist"                    bash -c 'grep -q "variable_resume_pre_purge_retract" "$0/config/acepro_macros.cfg" && grep -q "variable_resume_extra_prime: 0.0" "$0/config/acepro_macros.cfg"' "$REPO"

echo "18. Review fixes"
check "Z hop uses min_zhop and zhop_lift"            bash -c 'grep -q "curz < min_zhop" "$0/config/acepro_macros.cfg" && grep -q "curz + zhop_lift" "$0/config/acepro_macros.cfg"' "$REPO"
check "blade moves check positions"                  bash -c 'for m in TO_BLADE TO_FRONT_OF_THROW_BLADE TO_FRONT_OF_THROW_BLADE_2 TO_FRONT_OF_THROW_BLADE_SLOW; do awk -v m="$m" "\$0==\"[gcode_macro \" m \"]\"{f=1;next} f&&/^gcode:/{g=1;next} g&&NF{print \$1; exit}" "$0/config/acepro.cfg" | grep -qx _ACE_REQUIRE_POSITIONS || exit 1; done' "$REPO"
check "no fixed 2.5 left in the zigzag wipe"         bash -c '! sed -n "/gcode_macro _WIPE_ZIGZAG/,/Servo Shake Macro/p" "$0/config/acepro_macros.cfg" | grep -q "[+-] 2.5}"' "$REPO"
check "no commented-out G9111 macro left"            bash -c '! grep -q "^# *\[gcode_macro G9111\]" "$0/config/acepro.cfg"' "$REPO"

echo "Passed: $PASS   Failed: $FAIL"
[ "$FAIL" -eq 0 ]
