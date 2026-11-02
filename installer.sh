#!/bin/bash

# =============================================================================
# ACE Pro for Klipper - installer
# =============================================================================
# One installer for three kinds of printer software:
#   Klipper      mainline Klipper (Voron, RatRig, ...)
#   Kalico       the Klipper fork
#   Simple AF    Pellcorp's Simple AF (Creality K1 family, Kalico based)
#
# ./installer.sh                 install (asks a few plain questions first)
# ./installer.sh --update        update the driver and macros, keep your settings
# ./installer.sh --check         report problems, change nothing
# ./installer.sh --repair        restore links and includes (for example after a Simple AF update)
# ./installer.sh --undo [DIR]    put back the files saved before the last install
# ./installer.sh --support-bundle  collect logs and config (secrets removed) to share
# ./installer.sh --dry-run       go through the questions, show what would change, change nothing
# ./installer.sh --help
#
# Compatible with: Raspberry Pi OS, Debian, Ubuntu. Needs bash and python3.
# =============================================================================

set -u

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
DIM='\033[2m'
NC='\033[0m' # No Color

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/VERSION" 2>/dev/null || true)"
VERSION="${VERSION:-dev}"

# Resolve installation user/home for defaults (works when run via sudo).
INSTALL_USER="${SUDO_USER:-$(id -un)}"
INSTALL_HOME="$(getent passwd "$INSTALL_USER" 2>/dev/null | cut -d: -f6 || true)"
[ -n "$INSTALL_HOME" ] || INSTALL_HOME="$HOME"
INSTALL_HOME="${ACE_INSTALL_HOME:-$INSTALL_HOME}"      # tests point this at a fake home

TESTING="${ACE_INSTALLER_TEST:-0}"                     # 1 = never restart services, never run pip
MODE="install"
DRY=0
UNDO_ARG=""
KLIPPER_DIR="${ACE_KLIPPER_DIR:-}"
CONFIG_DIR="${ACE_CONFIG_DIR:-}"
BACKUP_ROOT="$INSTALL_HOME/acepro-backup"
MOONRAKER_URL="http://127.0.0.1:7125"
CFG_TOOL="$SCRIPT_DIR/tools/ace_cfg_tool.py"
VALIDATOR="$SCRIPT_DIR/tools/validate_config.py"

# Answers (filled by the questions, or read from acepro-install.conf on update)
PROFILE=""
ACE_COUNT=1
NOZZLE_PIN=""
HAVE_RDM=0;     RDM_PIN=""
HAVE_ENCODER=0; ENCODER_PIN=""
HAVE_SERVO=0;   SERVO_PIN=""
HAVE_CUTTER=1
HAVE_POOP=1
WANT_FLUIDD=0
WANT_KS=0
WANT_SPOOLMAN=0
WANT_CUTCAL=0
UPDATING=0            # 1 = an ACE install was found and we keep its values
STAGE=""
BACKUP_DIR=""
MOONRAKER_RESTART_NEEDED=0
FLUIDD_DIR=""
HOOKS_INCLUDE="auto"      # auto = installer adds the include line, manual = you add it in Fluidd, present = already included
HOOKS_FILE="my_saf_hooks.cfg"
HOOKS_SUMMARY=""          # what the installer changes in my_saf_hooks.cfg (shown in the plan)
HOOKS_ELSEWHERE=""        # hook macros that are defined in another file (not touched)
declare -a PROFILE_CHAIN=()
declare -a WARNINGS=()

# ============================================================================
# Output helpers
# ============================================================================

print_header() { echo -e "\n${BLUE}── $1 ──────────────────────────────────────────${NC}"; }
print_info()    { echo -e "${BLUE}ℹ ${1}${NC}"; }
print_success() { echo -e "${GREEN}✓ ${1}${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ ${1}${NC}"; }
print_error()   { echo -e "${RED}✗ ${1}${NC}"; }
why()           { echo -e "  ${DIM}Why: $1${NC}"; }
warn_later()    { WARNINGS+=("$1"); }

# Stop with a plain message and the exact fix. Nothing is half installed because
# nothing is changed before the summary is confirmed.
die_with_fix() {
    local msg="$1" fix="$2"
    print_error "Can't continue: $msg"
    [ -n "$fix" ] && echo -e "  Fix: $fix"
    echo "  Nothing was changed."
    exit 1
}

cleanup() { [ -n "${STAGE:-}" ] && [ -d "$STAGE" ] && rm -rf "$STAGE"; [ -n "${OVERLAY:-}" ] && [ -d "${OVERLAY:-}" ] && rm -rf "$OVERLAY"; return 0; }
trap cleanup EXIT

# ============================================================================
# Questions
# ============================================================================

# ask_yn "Question" Y|N ["why"]  -> returns 0 for yes. An empty answer (or no input at all) gives the default.
ask_yn() {
    local q="$1" def="${2:-N}" w="${3:-}" hint ans
    [ -n "$w" ] && why "$w"
    if [ "$def" = "Y" ]; then hint="[Y/n]"; else hint="[y/N]"; fi
    while true; do
        read -r -p "$(echo -e "${BLUE}${q}${NC} ${hint}: ")" ans || ans=""
        ans="${ans:-$def}"
        case "$ans" in
            [yY]*) return 0 ;;
            [nN]*) return 1 ;;
            *) echo "  Please answer y or n" ;;
        esac
    done
}

# ask_text "Question" "default" -> answer on stdout
ask_text() {
    local q="$1" def="${2:-}" ans
    if [ -n "$def" ]; then
        read -r -p "$(echo -e "${BLUE}${q}${NC} [${def}]: ")" ans || ans=""
    else
        read -r -p "$(echo -e "${BLUE}${q}${NC}: ")" ans || ans=""
    fi
    echo "${ans:-$def}"
}

valid_pin() { [[ "$1" =~ ^[!^~]*([A-Za-z0-9_]+:)?[!^~]*[A-Za-z0-9_/]+$ ]]; }

# ask_pin "Question" "default"   -> the pin is left in $PIN. Asks again until it looks like a pin.
PIN=""
ask_pin() {
    local q="$1" def="${2:-}" ans tries=0
    while true; do
        ans="$(ask_text "$q" "$def")"
        if [ -n "$ans" ] && valid_pin "$ans"; then PIN="$ans"; return 0; fi
        tries=$((tries + 1))
        if [ "$tries" -ge 5 ]; then
            die_with_fix "no valid pin was given for: $q" "Look up the pin in your printer.cfg (it looks like PA4 or nozzle_mcu:PA8) and run ./installer.sh again."
        fi
        echo "  That does not look like a pin. Examples: PA4, nozzle_mcu:PA8, ^PC15, gpiochip0/gpio26" >&2
    done
}

# ============================================================================
# Small helpers
# ============================================================================

cfg_tool() { python3 -I "$CFG_TOOL" "$@"; }

# Python that has Klipper's packages (jinja2). Falls back to system python3.
klippy_python() {
    local p="$INSTALL_HOME/klippy-env/bin/python"
    if [ -x "$p" ]; then echo "$p"; else command -v python3; fi
}

cfg_get() { cfg_tool get "$1" "$2" "$3" 2>/dev/null | head -1; }     # file section key

is_symlink() { [ -L "$1" ]; }

timestamp() { date +"%Y%m%d_%H%M%S"; }

kv_get() { # file key
    [ -f "$1" ] || return 1
    sed -n "s/^$2=\"\{0,1\}\(.*[^\"]\)\"\{0,1\}$/\1/p" "$1" | head -1
}

# Record a file in the backup before it is changed, so --undo can restore it.
backup_path() {
    local p="$1"
    [ -n "$BACKUP_DIR" ] || return 0
    # only the first (original) state of a file is saved; later edits in the same run must not overwrite it
    grep -qxF -e "MOD $p" -e "NEW $p" "$BACKUP_DIR/manifest.txt" 2>/dev/null && return 0
    if [ -e "$p" ] || is_symlink "$p"; then
        mkdir -p "$BACKUP_DIR/files$(dirname "$p")"
        cp -a "$p" "$BACKUP_DIR/files$p" 2>/dev/null
        echo "MOD $p" >> "$BACKUP_DIR/manifest.txt"
    else
        echo "NEW $p" >> "$BACKUP_DIR/manifest.txt"
    fi
}

# ============================================================================
# Profile (Klipper / Kalico / Simple AF)
# ============================================================================

detect_profile() {
    if [ -d "$INSTALL_HOME/pellcorp" ] || [ -f "$INSTALL_HOME/pellcorp.done" ]; then echo saf; return; fi
    local k="${KLIPPER_DIR:-$INSTALL_HOME/klipper}"
    if [ -f "$k/klippy/extras/danger_options.py" ]; then echo kalico; return; fi
    echo klipper
}

load_profile() { # profile -> sets PROFILE_NAME, SAF_HOOKS, PROFILE_CHAIN
    local p="$1" conf inherit
    PROFILE_CHAIN=()
    while [ -n "$p" ]; do
        conf="$SCRIPT_DIR/profiles/$p/profile.conf"
        [ -f "$conf" ] || die_with_fix "profile '$p' not found in this download" "Run: cd $SCRIPT_DIR && git pull"
        PROFILE_CHAIN+=("$p")
        if [ "${#PROFILE_CHAIN[@]}" -eq 1 ]; then
            PROFILE_NAME="$(kv_get "$conf" NAME)"
            SAF_HOOKS="$(kv_get "$conf" SAF_HOOKS)"
        fi
        inherit="$(kv_get "$conf" INHERIT)"
        p="$inherit"
    done
}

profile_file() { # name -> full path of the first profile in the chain that has it
    local p
    for p in "${PROFILE_CHAIN[@]}"; do
        [ -f "$SCRIPT_DIR/profiles/$p/$1" ] && { echo "$SCRIPT_DIR/profiles/$p/$1"; return 0; }
    done
    return 1
}

choose_profile() {
    local det choice def
    det="$(detect_profile)"
    case "$det" in klipper) def=1 ;; kalico) def=2 ;; saf) def=3 ;; esac
    print_header "1 of 7 · Your printer software"
    echo "Which software is your printer running?"
    echo "  1) Klipper"
    echo "  2) Kalico"
    echo "  3) Simple AF (Creality, Pellcorp)"
    why "this decides which files are installed and which macros we leave alone."
    case "$det" in
        saf) print_info "I found Simple AF in ~/pellcorp, so 3 is suggested." ;;
        kalico) print_info "I found Kalico files in your Klipper folder, so 2 is suggested." ;;
    esac
    while true; do
        read -r -p "$(echo -e "${BLUE}Choose${NC} [$def]: ")" choice || choice=""
        choice="${choice:-$def}"
        case "$choice" in
            1) PROFILE=klipper; break ;;
            2) PROFILE=kalico; break ;;
            3) PROFILE=saf; break ;;
            *) echo "  Please type 1, 2 or 3" ;;
        esac
    done
}

# ============================================================================
# Folders
# ============================================================================

find_dirs() {
    if [ -z "$KLIPPER_DIR" ]; then
        KLIPPER_DIR="$INSTALL_HOME/klipper"
        if [ ! -d "$KLIPPER_DIR/klippy" ]; then
            print_warning "I did not find Klipper at $KLIPPER_DIR"
            why "the driver is linked into Klipper's klippy/extras folder."
            KLIPPER_DIR="$(ask_text "Where is Klipper installed?" "$KLIPPER_DIR")"
        fi
    fi
    [ -d "$KLIPPER_DIR/klippy/extras" ] || die_with_fix "Klipper was not found at $KLIPPER_DIR" \
        "find it with   ls ~ | grep -i klipper   then run   ./installer.sh --klipper-dir /path/to/klipper"
    if [ -z "$CONFIG_DIR" ]; then
        CONFIG_DIR="$INSTALL_HOME/printer_data/config"
        if [ ! -d "$CONFIG_DIR" ]; then
            print_warning "I did not find the config folder at $CONFIG_DIR"
            CONFIG_DIR="$(ask_text "Where is your printer.cfg folder?" "$CONFIG_DIR")"
        fi
    fi
    [ -d "$CONFIG_DIR" ] || die_with_fix "the config folder was not found at $CONFIG_DIR" \
        "run   ./installer.sh --config-dir /path/to/config   (the folder that holds printer.cfg)"
    print_success "Klipper: $KLIPPER_DIR    Config: $CONFIG_DIR"
}

# ============================================================================
# Saved answers
# ============================================================================

CONF_FILE() { echo "$CONFIG_DIR/acepro-install.conf"; }

save_answers() {
    local f; f="$(CONF_FILE)"
    {
        echo "# Written by installer.sh. ./installer.sh --update reuses these. Safe to delete."
        echo "VERSION=\"$VERSION\""
        echo "PROFILE=\"$PROFILE\""
        echo "ACE_COUNT=\"$ACE_COUNT\""
        echo "HAVE_SERVO=\"$HAVE_SERVO\""
        echo "HAVE_CUTTER=\"$HAVE_CUTTER\""
        echo "HAVE_POOP=\"$HAVE_POOP\""
        echo "KLIPPER_DIR=\"$KLIPPER_DIR\""
    } > "$f"
}

# Pi 5 + PCIe USB HAT: newer 6.12.x kernels fail to start the HAT's USB controller
# (xhci "can't setup: -12", raspberrypi/linux #7715). Warn and offer the kernel pin.
check_pi5_usb_hat() {
    [ "$TESTING" = 1 ] && return 0
    grep -qa "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null || return 0
    local log
    log="$( { dmesg 2>/dev/null; journalctl -k --no-pager 2>/dev/null; } | grep -iE "xhci.*(can't setup|probe.*failed)" | head -2 )"
    [ -n "$log" ] || return 0

    print_header "Pi 5 USB HAT problem detected"
    print_warning "The kernel log shows the USB HAT controller failing to start:"
    echo "$log" | sed 's/^/    /'
    print_info "Without it Klipper cannot see the ACE units or the MCUs behind the HAT."
    print_info "Known upstream issue: raspberrypi/linux #7715 (newer 6.12.x kernels). See README section 14."
    if [ -f "$SCRIPT_DIR/tools/pin-pi5-kernel.sh" ] && ask_yn "Pin the last working kernel (6.12.96) now? Needs sudo and a reboot." N; then
        if sudo bash "$SCRIPT_DIR/tools/pin-pi5-kernel.sh"; then
            print_success "Kernel pinned. Reboot when the installation is finished, then check: dmesg | grep -i xhci"
        else
            print_warning "Pinning failed. Run it by hand later: sudo bash tools/pin-pi5-kernel.sh --check"
        fi
    fi
}

# ============================================================================
# Questions 2 to 5 (fresh install)
# ============================================================================

# Simple AF hooks file (my_saf_hooks.cfg). If you have one, it is UPDATED: your lines stay, the ACE lines
# are added at the top of each hook macro. If you have none, a new one is written.
hooks_included_by() { # -> file that already includes my_saf_hooks.cfg (empty if none)
    grep -lE '^[[:space:]]*\[include[[:space:]]+(\./)?my_saf_hooks\.cfg\]' "$CONFIG_DIR"/*.cfg 2>/dev/null | head -1
}

hooks_defined_elsewhere() { # -> "name,name" of hook macros that another file already defines
    local name f out=""
    for name in $(cfg_tool hooknames "$(profile_file my_saf_hooks.cfg)"); do
        for f in "$CONFIG_DIR"/*.cfg; do
            [ -f "$f" ] || continue
            case "$(basename "$f")" in "$HOOKS_FILE"|printer-*.cfg|*.backup*) continue ;; esac
            if grep -qE "^\[gcode_macro[[:space:]]+$name\]" "$f"; then out="$out,$name"; break; fi
        done
    done
    echo "${out#,}"
}

ask_hooks_include() {
    [ "$PROFILE" = "saf" ] || return 0
    local by; by="$(hooks_included_by)"
    print_header "5b · Simple AF hooks ($HOOKS_FILE)"
    echo "Simple AF can run your own steps at set moments (homing, start, end, pause, resume, cancel)."
    if [ -f "$CONFIG_DIR/$HOOKS_FILE" ]; then
        echo "You already have $HOOKS_FILE. The installer will UPDATE it: your own lines stay as they are,"
        echo "and the ACE lines are added at the top of each hook (the encoder lines only if you have that sensor)."
    else
        echo "The installer will write $HOOKS_FILE with the ACE steps for those moments."
    fi
    if [ -n "$by" ]; then
        HOOKS_INCLUDE=present
        print_info "$(basename "$by") already includes $HOOKS_FILE, nothing to add to printer.cfg."
        return 0
    fi
    why "the file only takes effect when printer.cfg includes it."
    if ask_yn "Let the installer add [include $HOOKS_FILE] to printer.cfg?" Y "choose no to add the line yourself in Fluidd (the installer will tell you where)."; then
        HOOKS_INCLUDE=auto
    else
        HOOKS_INCLUDE=manual
    fi
}

ask_hardware() {
    local cur_nozzle=""
    print_header "2 of 7 · Your ACE Pro"
    why "1 unit gives tools T0-T3, 2 units give T0-T7."
    ACE_COUNT="$(ask_text "How many ACE Pro units are connected? (1 or 2)" "1")"
    case "$ACE_COUNT" in 1|2|3) ;; *) ACE_COUNT=1 ;; esac
    echo
    echo "The ACE driver needs a filament sensor at the toolhead (before the extruder gears)."
    why "without it the driver cannot tell when a load worked."
    ask_pin "Pin of the toolhead filament sensor (for example PA4 or nozzle_mcu:PA8)" "$cur_nozzle"; NOZZLE_PIN="$PIN"
    if ask_yn "Do you have an RDM sensor (after the filament splitter)?" N "optional; the installer leaves it out if you say no."; then
        HAVE_RDM=1; ask_pin "RDM sensor pin" ""; RDM_PIN="$PIN"
    fi
    if ask_yn "Do you have the ACE encoder sensor (filament motion sensor on the extruder)?" N "optional; it detects a blocked extruder."; then
        HAVE_ENCODER=1; ask_pin "Encoder sensor pin" ""; ENCODER_PIN="$PIN"
    fi

    print_header "3 of 7 · Servo poop basket"
    if ask_yn "Do you have the servo poop basket?" N "with no, the servo is switched off and its section is left out of your config."; then
        HAVE_SERVO=1; ask_pin "Servo signal pin (for example PB14)" ""; SERVO_PIN="$PIN"
    fi

    print_header "4 of 7 · Cutter and poop bucket"
    if ask_yn "Do you have a filament cutter?" Y "no switches CUT_TIP off."; then HAVE_CUTTER=1; else HAVE_CUTTER=0; fi
    if ask_yn "Do you have a poop bucket?" Y "no switches FLUSH_POOP off. Without a bucket the purged filament lands where the nozzle is."; then HAVE_POOP=1; else HAVE_POOP=0; fi
    echo "The cutter, bucket, wipe and park positions start as placeholders. Moves to them stay"
    echo "blocked until you measure them (the list is printed at the end)."

    print_header "5 of 7 · Extras (all optional)"
    FLUIDD_DIR="$INSTALL_HOME/fluidd"
    if [ -d "$FLUIDD_DIR" ]; then
        ask_yn "Install the Fluidd ACE panel (spool picker and status card)?" Y "replaces ~/fluidd with a build that has the ACE card; your Fluidd settings are kept and the old files are backed up." && WANT_FLUIDD=1
    else
        print_info "Fluidd not found in $FLUIDD_DIR, so the Fluidd panel is skipped."
    fi
    if [ -d "$INSTALL_HOME/KlipperScreen/panels" ]; then
        ask_yn "Add the ACE menu to KlipperScreen?" Y "links the ACE panel and adds menu entries." && WANT_KS=1
    fi
    ask_yn "Add the Spoolman helpers?" N "only if you use Spoolman." && WANT_SPOOLMAN=1
    ask_yn "Add the cutter calibration macros (CUT_CAL_START ...)?" N "helps you find where the cutter closes." && WANT_CUTCAL=1
    ask_hooks_include
}

# ============================================================================
# Build the new files in a staging folder
# ============================================================================

OLD() { echo "$CONFIG_DIR/$1"; }

stage_files() {
    local f
    STAGE="$(mktemp -d)"
    for f in acepro.cfg acepro_setting.cfg acepro_macros.cfg acepro_printer_macros.cfg; do
        cp "$SCRIPT_DIR/config/$f" "$STAGE/$f"
    done

    # Simple AF hooks: update your my_saf_hooks.cfg (or write a new one). The encoder lines stay only
    # if you have the ACE encoder sensor.
    HOOKS_SUMMARY=""; HOOKS_ELSEWHERE=""
    if [ "$SAF_HOOKS" = "yes" ]; then
        local enc=$HAVE_ENCODER cur="-"
        if [ "$UPDATING" = 1 ]; then
            enc=0; grep -qE '^\[filament_motion_sensor ace_encoder\]' "$(OLD acepro.cfg)" 2>/dev/null && enc=1
        fi
        [ -f "$CONFIG_DIR/$HOOKS_FILE" ] && cur="$CONFIG_DIR/$HOOKS_FILE"
        HOOKS_ELSEWHERE="$(hooks_defined_elsewhere)"
        HOOKS_SUMMARY="$(cfg_tool hooks "$(profile_file my_saf_hooks.cfg)" "$cur" "$STAGE/$HOOKS_FILE" "$enc" "$HOOKS_ELSEWHERE")"
    fi

    [ "$WANT_SPOOLMAN" = 1 ] && cp "$SCRIPT_DIR/config/spoolman_logic.cfg" "$STAGE/spoolman_logic.cfg"
    [ "$WANT_CUTCAL" = 1 ] && cp "$SCRIPT_DIR/config/cut_calibrate.cfg" "$STAGE/cut_calibrate.cfg"

    if [ "$UPDATING" = 1 ]; then
        stage_update_values
    else
        stage_fresh_values
    fi
}

write_servo_cfg() { # path pin
    cat > "$1" <<EOF
# Written by installer.sh. The servo that opens the poop basket.
# Wrong pin? Change it here. No servo? Delete this file and set variable_servo_enable: False
# in acepro_macros.cfg (_ACE_VARS).
[servo servo_wipe] # EZMAX ES3004 SERVO
pin: $2
maximum_servo_angle: 145              # Maximum angle (degrees)
minimum_pulse_width: 0.0007           # Pulse width for 0 degrees
maximum_pulse_width: 0.0023           # Pulse width for 145 degrees
initial_angle: 0                      # Set to 0 degrees at startup
EOF
}

stage_fresh_values() {
    cfg_tool set "$STAGE/acepro_setting.cfg" ace ace_count "$ACE_COUNT" || true
    cfg_tool set "$STAGE/acepro.cfg" "filament_switch_sensor filament_runout_nozzle" switch_pin "$NOZZLE_PIN"
    if [ "$HAVE_RDM" = 1 ]; then
        cfg_tool set "$STAGE/acepro.cfg" "filament_switch_sensor filament_runout_rdm" switch_pin "$RDM_PIN"
    else
        cfg_tool comment "$STAGE/acepro.cfg" "filament_switch_sensor filament_runout_rdm" "Left out by installer.sh: no RDM sensor."
        sed -i 's/^filament_runout_sensor_name_rdm:/#filament_runout_sensor_name_rdm:/' "$STAGE/acepro_setting.cfg"
    fi
    if [ "$HAVE_ENCODER" = 1 ]; then
        cfg_tool set "$STAGE/acepro.cfg" "filament_motion_sensor ace_encoder" switch_pin "$ENCODER_PIN"
    else
        cfg_tool comment "$STAGE/acepro.cfg" "filament_motion_sensor ace_encoder" "Left out by installer.sh: no encoder sensor."
    fi
    if [ "$HAVE_SERVO" = 1 ]; then
        write_servo_cfg "$STAGE/acepro_servo.cfg" "$SERVO_PIN"
    else
        cfg_tool set "$STAGE/acepro_macros.cfg" "gcode_macro _ACE_VARS" variable_servo_enable False
    fi
    [ "$HAVE_CUTTER" = 1 ] || cfg_tool set "$STAGE/acepro_macros.cfg" "gcode_macro _ACE_VARS" variable_cutter_enable False
    [ "$HAVE_POOP" = 1 ]   || cfg_tool set "$STAGE/acepro_macros.cfg" "gcode_macro _ACE_VARS" variable_poop_enable False
    cfg_tool set "$STAGE/acepro_macros.cfg" "gcode_macro _ACE_VARS" variable_positions_confirmed False
}

# An ACE install is already there: keep its values, take the new code.
stage_update_values() {
    local f n total=0 oldpm
    for f in acepro.cfg acepro_setting.cfg acepro_macros.cfg; do
        if [ -f "$(OLD $f)" ]; then
            n="$(cfg_tool carry "$(OLD $f)" "$STAGE/$f" 2>/dev/null || echo 0)"
            total=$((total + ${n:-0}))
        fi
    done
    # Optional sensors that were left out before stay left out
    if [ -f "$(OLD acepro.cfg)" ]; then
        grep -qE '^\[filament_switch_sensor filament_runout_rdm\]' "$(OLD acepro.cfg)" || {
            cfg_tool comment "$STAGE/acepro.cfg" "filament_switch_sensor filament_runout_rdm" "Left out (as in your earlier install)." || true
            sed -i 's/^filament_runout_sensor_name_rdm:/#filament_runout_sensor_name_rdm:/' "$STAGE/acepro_setting.cfg"; }
        grep -qE '^\[filament_motion_sensor ace_encoder\]' "$(OLD acepro.cfg)" || \
            cfg_tool comment "$STAGE/acepro.cfg" "filament_motion_sensor ace_encoder" "Left out (as in your earlier install)." || true
    fi
    if [ -f "$(OLD acepro_setting.cfg)" ] && ! grep -qE '^filament_runout_sensor_name_rdm:' "$(OLD acepro_setting.cfg)"; then
        sed -i 's/^filament_runout_sensor_name_rdm:/#filament_runout_sensor_name_rdm:/' "$STAGE/acepro_setting.cfg"
    fi
    # Servo: keep acepro_servo.cfg, or move the [servo] block out of an older acepro_macros.cfg
    if [ -f "$(OLD acepro_servo.cfg)" ]; then
        cp "$(OLD acepro_servo.cfg)" "$STAGE/acepro_servo.cfg"
    elif [ -f "$(OLD acepro_macros.cfg)" ] && block="$(cfg_tool servo "$(OLD acepro_macros.cfg)" 2>/dev/null)" && [ -n "$block" ]; then
        { echo "# Moved here by installer.sh from acepro_macros.cfg (your pin and angles are unchanged)."; echo "$block"; } > "$STAGE/acepro_servo.cfg"
        print_info "Moved your [servo servo_wipe] section into acepro_servo.cfg"
    fi
    [ -f "$(OLD acepro_printer_macros.cfg)" ] && cfg_tool carry "$(OLD acepro_printer_macros.cfg)" "$STAGE/acepro_printer_macros.cfg" >/dev/null 2>&1
    print_info "Kept $total of your settings from the current files."
}

# ============================================================================
# The plan, and a check of the result before anything is written
# ============================================================================

declare -a PLAN_LINES=()
plan_stage() {
    local f t state
    PLAN_LINES=()
    for f in "$STAGE"/*; do
        f="$(basename "$f")"; t="$CONFIG_DIR/$f"
        if [ ! -e "$t" ] && ! is_symlink "$t"; then state="NEW     "
        elif cmp -s "$STAGE/$f" "$t"; then state="same    "
        else state="UPDATE  "; fi
        PLAN_LINES+=("$state$t")
    done
}

include_present() { grep -qE '^\s*\[include\s+acepro\.cfg\]' "$CONFIG_DIR/printer.cfg" 2>/dev/null; }

show_plan() {
    local l
    plan_stage
    for l in "${PLAN_LINES[@]}"; do echo "  $l"; done
    include_present && echo "  ok      printer.cfg already has [include acepro.cfg]" || echo "  EDIT    printer.cfg (+1 include line at the top)"
    echo "  LINK    $KLIPPER_DIR/klippy/extras/ace → $SCRIPT_DIR/extras/ace"
    if [ "$PROFILE" = "saf" ]; then
        echo "  SKIP    moonraker.conf (never touched on Simple AF)"
        local hl
        if [ -n "$HOOKS_SUMMARY" ]; then
            while IFS= read -r hl; do [ -n "$hl" ] && echo "            $HOOKS_FILE: $hl"; done <<<"$HOOKS_SUMMARY"
        fi
        case "$HOOKS_INCLUDE" in
            auto)   grep -qF "[include $HOOKS_FILE]" "$CONFIG_DIR/printer.cfg" 2>/dev/null || echo "  EDIT    printer.cfg (+ [include $HOOKS_FILE] below the ACE include)" ;;
            manual) echo "  NOTE    you add [include $HOOKS_FILE] to printer.cfg yourself (Fluidd)" ;;
        esac
        [ -n "$HOOKS_ELSEWHERE" ] && echo "  NOTE    hooks defined in another file are not touched: $HOOKS_ELSEWHERE"
    fi
    [ "$WANT_FLUIDD" = 1 ] && echo "  PANEL   Fluidd ACE panel (old Fluidd saved as ${FLUIDD_DIR}_backup_*)"
    [ "$WANT_KS" = 1 ] && echo "  PANEL   KlipperScreen ACE menu"
}

# Run the validator on a copy of the config with the new files in it. Only problems the
# new files would ADD count; problems that are already in your config are shown but do not stop you.
check_overlay() {
    local py base_out new_out line new=0
    py="$(klippy_python)"
    OVERLAY="$(mktemp -d)"
    cp -a "$CONFIG_DIR/." "$OVERLAY/" 2>/dev/null
    local f
    for f in "$STAGE"/*; do rm -f "$OVERLAY/$(basename "$f")"; cp "$f" "$OVERLAY/"; done
    if [ -f "$OVERLAY/printer.cfg" ] && ! grep -qE '^\s*\[include\s+acepro\.cfg\]' "$OVERLAY/printer.cfg"; then
        { echo "[include acepro.cfg]"; echo; cat "$OVERLAY/printer.cfg"; } > "$OVERLAY/printer.cfg.new" && mv "$OVERLAY/printer.cfg.new" "$OVERLAY/printer.cfg"
    elif [ ! -f "$OVERLAY/printer.cfg" ]; then
        echo "[include acepro.cfg]" > "$OVERLAY/printer.cfg"
    fi
    base_out="$("$py" "$VALIDATOR" "$CONFIG_DIR/printer.cfg" --profile "$PROFILE" 2>&1 | grep '^ERROR' || true)"
    new_out="$("$py" "$VALIDATOR" "$OVERLAY/printer.cfg" --profile "$PROFILE" 2>&1 | sed "s#$OVERLAY#$CONFIG_DIR#g" | grep '^ERROR' || true)"
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        if ! grep -qxF "$line" <<<"$base_out"; then
            new=$((new + 1)); print_error "${line#ERROR:   }"
        fi
    done <<<"$new_out"
    "$py" "$VALIDATOR" "$OVERLAY/printer.cfg" --profile "$PROFILE" 2>&1 | sed "s#$OVERLAY#$CONFIG_DIR#g" | grep -E '^(warning|note):' | sed 's/^/    /' || true
    rm -rf "$OVERLAY"; OVERLAY=""
    return $((new > 0))
}

# ============================================================================
# Writing things
# ============================================================================

ensure_include_in_printer_cfg() {
    local pc="$CONFIG_DIR/printer.cfg" tmp
    if [ ! -f "$pc" ]; then
        backup_path "$pc"; echo "[include acepro.cfg]" > "$pc"; print_success "Created printer.cfg with the include line"; return
    fi
    if include_present; then print_success "printer.cfg already includes acepro.cfg"; return; fi
    backup_path "$pc"
    tmp="$(mktemp)"
    { echo "[include acepro.cfg]"; echo; cat "$pc"; } > "$tmp" && cat "$tmp" > "$pc" && rm -f "$tmp"
    print_success "Added [include acepro.cfg] at the top of printer.cfg"
}

ensure_include_line() { # line
    local pc="$CONFIG_DIR/printer.cfg" tmp
    grep -qF "$1" "$pc" && return 0
    backup_path "$pc"
    tmp="$(mktemp)"
    awk -v line="$1" '{print} /^[[:space:]]*\[include[[:space:]]+acepro\.cfg\]/ && !d {print line; d=1} END{if(!d) print line}' "$pc" > "$tmp" && cat "$tmp" > "$pc" && rm -f "$tmp"
    print_success "Added $1 to printer.cfg"
}

ensure_force_move() {
    local pc="$CONFIG_DIR/printer.cfg"
    [ -f "$pc" ] || return 0
    if grep -qE '^[[:space:]]*\[force_move\]' "$pc"; then
        grep -qiE '^[[:space:]]*enable_force_move[[:space:]]*:[[:space:]]*true' "$pc" || \
            warn_later "printer.cfg has [force_move] but enable_force_move is not True. CUT_TIP needs it."
        return 0
    fi
    backup_path "$pc"
    printf '\n[force_move]\nenable_force_move: True\n' >> "$pc"
    print_success "Added [force_move] enable_force_move: True to printer.cfg (CUT_TIP needs it)"
}

apply_stage() {
    local f t
    for f in "$STAGE"/*; do
        f="$(basename "$f")"; t="$CONFIG_DIR/$f"
        if [ -e "$t" ] && cmp -s "$STAGE/$f" "$t"; then continue; fi
        backup_path "$t"
        is_symlink "$t" && rm -f "$t"
        cp "$STAGE/$f" "$t"
        print_success "Wrote $t"
    done
}

link_item() { # source target label
    local src="$1" dst="$2" label="$3" old
    [ -e "$src" ] || { print_warning "$label: $src is missing, skipped"; return 1; }
    if is_symlink "$dst" && [ "$(readlink "$dst")" = "$src" ]; then print_success "$label already linked"; return 0; fi
    if [ -e "$dst" ] && ! is_symlink "$dst"; then
        if [ "$label" = "virtual_pins" ] && grep -q "virtual_pin" "$dst" 2>/dev/null; then
            print_success "Klipper already has its own virtual_pins.py, keeping it"; return 0
        fi
        warn_later "$dst already exists and is not a link, so I left it alone ($label)."; return 1
    fi
    if is_symlink "$dst"; then old="$(readlink "$dst")"; echo "LINK $dst $old" >> "$BACKUP_DIR/manifest.txt"; rm -f "$dst"
    else echo "LINK $dst -" >> "$BACKUP_DIR/manifest.txt"; fi
    mkdir -p "$(dirname "$dst")"
    ln -s "$src" "$dst" && print_success "Linked $label"
}

link_driver() {
    local x="$KLIPPER_DIR/klippy/extras"
    link_item "$SCRIPT_DIR/extras/ace" "$x/ace" "ACE driver"
    link_item "$SCRIPT_DIR/extras/virtual_pins.py" "$x/virtual_pins.py" "virtual_pins"
    [ -f "$SCRIPT_DIR/extras/temperature_ace.py" ] && link_item "$SCRIPT_DIR/extras/temperature_ace.py" "$x/temperature_ace.py" "ACE temperature sensor"
}

stale_backup_links() { ls -d "$KLIPPER_DIR"/klippy/extras/ace_backup_* 2>/dev/null || true; }

remove_old_ace_dashboard() {
    local moonraker_conf="$CONFIG_DIR/moonraker.conf" f
    for f in "$INSTALL_HOME/moonraker/moonraker/components/ace_status.py" \
             "$INSTALL_HOME"/mainsail/{ace.html,ace-dashboard.js,ace-dashboard.css,ace-dashboard-config.js,favicon.svg} \
             "$INSTALL_HOME"/fluidd/{ace.html,ace-dashboard.js,ace-dashboard.css,ace-dashboard-config.js,favicon.svg}; do
        if [ -L "$f" ] && readlink "$f" | grep -q "acepro-mmu-dashboard"; then
            rm -f "$f" && print_success "Removed old dashboard link: $f"
        fi
    done
    # Simple AF owns moonraker.conf: never edit it there.
    [ "$PROFILE" = "saf" ] && return 0
    if [ -f "$moonraker_conf" ] && grep -qi '^[[:space:]]*\[ace_status\][[:space:]]*$' "$moonraker_conf"; then
        if awk '/^[[:space:]]*\[ace_status\]/{f=1;next} f&&/^[[:space:]]*\[/{exit} f&&/^[^#[:space:]]/{found=1} END{exit found?0:1}' "$moonraker_conf"; then
            warn_later "$moonraker_conf: [ace_status] has settings, left as is. Remove it yourself, the component is gone."
        else
            backup_path "$moonraker_conf"
            sed -i -e '/^[[:space:]]*\[ace_status\][[:space:]]*$/d' -e '/^# ACE status extension$/d' "$moonraker_conf"
            print_success "Removed the empty [ace_status] section from moonraker.conf"
            MOONRAKER_RESTART_NEEDED=1
        fi
    fi
}

install_python_packages() {
    [ "$TESTING" = 1 ] && return 0
    local py; py="$(klippy_python)"
    if "$py" -c "import serial, jinja2" 2>/dev/null; then
        print_success "pyserial and jinja2 are available"
    else
        print_warning "pyserial or jinja2 is missing in $py"
        if ask_yn "Install them now (pip install pyserial jinja2)?" Y; then
            "$py" -m pip install "pyserial>=3.4" "jinja2>=3.0.0" && print_success "Packages installed" \
                || warn_later "pip failed. Run: $py -m pip install pyserial jinja2"
        fi
    fi
    "$py" -m compileall -q "$SCRIPT_DIR/extras" >/dev/null 2>&1 \
        && print_success "Driver files compile (syntax OK)" \
        || warn_later "The driver did not compile with $py. It needs Python 3.9 or newer."
}

# ---- Fluidd panel -----------------------------------------------------------
install_fluidd_panel() {
    local fluidd_dir="$1" zip="$SCRIPT_DIR/fluidd/fluidd-v1.37.7-acepro.zip" backup
    [ -f "$zip" ] || { warn_later "Fluidd build not found: $zip"; return 1; }
    if [ -f "$zip.sha256" ] && ! (cd "$SCRIPT_DIR/fluidd" && sha256sum -c "$(basename "$zip.sha256")" >/dev/null 2>&1); then
        warn_later "Checksum of the Fluidd build does not match. The panel was not installed."; return 1
    fi
    [ -d "$fluidd_dir" ] || { warn_later "Fluidd folder not found: $fluidd_dir"; return 1; }
    backup="${fluidd_dir}_backup_$(timestamp)"
    cp -a "$fluidd_dir" "$backup" && echo "FLUIDD $fluidd_dir $backup" >> "$BACKUP_DIR/manifest.txt"
    print_success "Backed up Fluidd → $backup"
    rm -rf "$fluidd_dir/assets"
    if command -v unzip >/dev/null 2>&1; then unzip -qo "$zip" -x config.json -d "$fluidd_dir"
    else python3 -I - "$zip" "$fluidd_dir" <<'PYZIP'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
for n in z.namelist():
    if n != "config.json":
        z.extract(n, sys.argv[2])
PYZIP
    fi
    [ -f "$fluidd_dir/config.json" ] || python3 -I -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extract('config.json', sys.argv[2])" "$zip" "$fluidd_dir"
    chmod -R a+rX "$fluidd_dir" 2>/dev/null || true
    if grep -rlq "Choose ACE spools" "$fluidd_dir/assets" 2>/dev/null; then
        print_success "Fluidd ACE panel installed (hard-refresh the browser to load it)"
    else
        print_error "The ACE panel was not found after unpacking. Restoring Fluidd."
        rm -rf "$fluidd_dir" && cp -a "$backup" "$fluidd_dir"; return 1
    fi
    if [ "$PROFILE" != "saf" ] && grep -qE '^\[update_manager[[:space:]]+fluidd\]' "$CONFIG_DIR/moonraker.conf" 2>/dev/null; then
        warn_later "moonraker.conf has [update_manager fluidd]: updating Fluidd there replaces this build. Run ./installer.sh --repair after a Fluidd update."
    fi
}

# ---- KlipperScreen ------------------------------------------------------------
ensure_menu_entry() { # conf header block label
    local conf="$1" header="$2" block="$3" tmp user_section
    user_section="$(sed '/^#~# --- Do not edit/,$d' "$conf" 2>/dev/null || cat "$conf" 2>/dev/null || true)"
    echo "$user_section" | grep -qF "$header" && return 0
    tmp="$(mktemp)"
    if grep -q '^#~# --- Do not edit' "$conf" 2>/dev/null; then
        awk -v block="$block" '/^#~# --- Do not edit/ && !done {print block; print ""; done=1} {print}' "$conf" > "$tmp" && cat "$tmp" > "$conf"
    else
        printf '\n%s\n' "$block" >> "$conf"
    fi
    rm -f "$tmp"
}

setup_klipperscreen() {
    local panels="$INSTALL_HOME/KlipperScreen/panels" conf="$CONFIG_DIR/KlipperScreen.conf"
    [ -d "$panels" ] || return 0
    link_item "$SCRIPT_DIR/KlipperScreen/acepro.py" "$panels/acepro.py" "KlipperScreen ACE panel"
    backup_path "$conf"
    [ -f "$conf" ] || printf '[main]\nfont_size = small\n' > "$conf"
    ensure_menu_entry "$conf" "[menu __main acepro]" $'[menu __main acepro]\nname: ACE Pro\nicon: settings\npanel: acepro' main
    ensure_menu_entry "$conf" "[menu __print acepro]" $'[menu __print acepro]\nname: ACE Pro\nicon: settings\npanel: acepro' print
    print_success "KlipperScreen: ACE Pro menu entries present"
}

# ============================================================================
# Restart and self-test
# ============================================================================

klippy_state() {
    curl -s -m 3 "$MOONRAKER_URL/server/info" 2>/dev/null | python3 -I -c 'import sys,json; print(json.load(sys.stdin)["result"]["klippy_state"])' 2>/dev/null || echo ""
}

restart_and_selftest() {
    local pass=0 fail=0 state="" objs n i
    if [ "$TESTING" = 1 ]; then print_info "Test mode: no restart"; return 0; fi
    if [ "$MOONRAKER_RESTART_NEEDED" = 1 ]; then ask_yn "Restart Moonraker now?" Y && sudo systemctl restart moonraker; fi
    if ask_yn "Restart Klipper now so the changes take effect?" Y; then
        sudo systemctl restart klipper || print_warning "Could not restart Klipper. Run: sudo systemctl restart klipper"
    else
        print_warning "Klipper not restarted. Run: sudo systemctl restart klipper"; return 0
    fi
    command -v curl >/dev/null 2>&1 || { print_info "curl is missing, so the self-test is skipped."; return 0; }
    print_info "Waiting for Klipper to start ..."
    for i in $(seq 1 30); do
        sleep 2; state="$(klippy_state)"
        case "$state" in ready|error|shutdown) break ;; esac
    done
    echo; echo "Self-test"
    if [ "$state" = "ready" ]; then print_success "Klipper is ready"; pass=$((pass+1)); else print_error "Klipper state: ${state:-unknown}. Read the error in Fluidd or ~/printer_data/logs/klippy.log"; fail=$((fail+1)); fi
    if [ "$state" = "ready" ]; then
        objs="$(curl -s -m 3 "$MOONRAKER_URL/printer/objects/list" | python3 -I -c 'import sys,json; o=json.load(sys.stdin)["result"]["objects"]; print(sum(1 for x in o if x=="ace" or x.startswith("ace_instance")))' 2>/dev/null || echo 0)"
        if [ "${objs:-0}" -gt 0 ] 2>/dev/null; then print_success "ACE driver loaded ($objs ACE objects)"; pass=$((pass+1)); else print_error "The ACE driver is not loaded. Check that printer.cfg has [include acepro.cfg]."; fail=$((fail+1)); fi
        n="$(curl -s -m 3 "$MOONRAKER_URL/printer/objects/list" | python3 -I -c 'import sys,json; o=json.load(sys.stdin)["result"]["objects"]; print(sum(1 for x in o if x.startswith("ace_instance")))' 2>/dev/null || echo 0)"
        if [ "${n:-0}" -ge "$ACE_COUNT" ] 2>/dev/null || [ "${n:-0}" = 0 ]; then print_success "ACE units found: expected $ACE_COUNT"; pass=$((pass+1)); else print_warning "Found $n ACE unit objects, expected $ACE_COUNT. Is every unit plugged in and powered?"; fail=$((fail+1)); fi
    fi
    echo; echo "Self-test: $pass passed, $fail failed"
    if [ "$state" != "ready" ] && [ "$state" != "" ] && [ -n "$BACKUP_DIR" ]; then
        if ask_yn "Klipper did not start. Put your old files back now?" Y "your files are saved in $BACKUP_DIR."; then do_undo "$BACKUP_DIR"; fi
    fi
}

# ============================================================================
# Final instructions
# ============================================================================

final_steps() {
    local n=1
    print_header "Done"
    local w; for w in "${WARNINGS[@]:-}"; do [ -n "$w" ] && print_warning "$w"; done
    cat <<EOF

What to do next
EOF
    if [ "$PROFILE" = "saf" ] && [ "$HOOKS_INCLUDE" = "manual" ] && [ -z "$(hooks_included_by)" ]; then
        cat <<EOT
 $n. Add this line to printer.cfg (Fluidd: Configuration, printer.cfg), right below [include acepro.cfg]:
      [include $HOOKS_FILE]
    Until you do, the Simple AF hooks (encoder, servo, pause, resume, cancel) do not run.
EOT
        n=$((n+1))
    fi
    if [ "$PROFILE" = "saf" ] && [ -n "$HOOKS_ELSEWHERE" ]; then
        local hn
        echo " $n. These hooks are defined in another file, so the installer did not touch them. Add the ACE lines there yourself:"
        for hn in ${HOOKS_ELSEWHERE//,/ }; do
            echo "      $hn  ->  $(cfg_tool hookcmds "$(profile_file my_saf_hooks.cfg)" "$hn")"
        done
        n=$((n+1))
    fi
    if [ "$UPDATING" = 0 ]; then
        cat <<EOF
 $n. Measure the positions in $CONFIG_DIR/acepro_macros.cfg (_ACE_VARS):
      cutter block X/Y and engage/full X/Y, poop bucket X/Y, wipe start X/Y, heat position,
      servo minimum Z. Then set  variable_positions_confirmed: True  (README section 4.3).
EOF
        n=$((n+1))
    fi
    cat <<EOF
 $n. OrcaSlicer, Machine start G-code (README section 5.1):
      M140 S0
      M104 S0
      MY_START_PRINT TOOL={initial_tool} BED_TEMP=[bed_temperature_initial_layer_single] EXTRUDER_TEMP=[nozzle_temperature_initial_layer]
      SET_PRINT_STATS_INFO TOTAL_LAYER=[total_layer_count]
EOF
    n=$((n+1))
    [ "$PROFILE" = "saf" ] && { echo "      (keep the other parameters Simple AF's own start G-code passes to START_PRINT)"; }
    cat <<EOF
 $n. First test in the console:  ACE_GET_STATUS   then   T0
 $((n+1)). OrcaSlicer plugin for choosing spools (runs on your computer): README section 5.3.

Undo this install:    ./installer.sh --undo
Check any time:       ./installer.sh --check
After an update of Simple AF or Fluidd:   ./installer.sh --repair
Problems?             ./installer.sh --support-bundle
EOF
}

# ============================================================================
# Modes: install / update
# ============================================================================

update_notice() {
    command -v git >/dev/null 2>&1 && [ -d "$SCRIPT_DIR/.git" ] || return 0
    [ "$TESTING" = 1 ] && return 0
    timeout 6 git -C "$SCRIPT_DIR" fetch -q 2>/dev/null || return 0
    local behind
    behind="$(git -C "$SCRIPT_DIR" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)"
    if [ "${behind:-0}" -gt 0 ] 2>/dev/null; then
        print_info "A newer version of this installer is on GitHub ($behind new commits)."
        echo "  Update it first:  cd $SCRIPT_DIR && git pull && ./installer.sh --update"
    fi
}

do_install() {
    local existing=0
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   ACE Pro for Klipper  ·  installer  v${VERSION}$(printf '%*s' $((19 - ${#VERSION})) '')║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
    echo "Nothing is changed until you confirm the summary. Press ENTER to accept the [default]."
    [ "$DRY" = 1 ] && print_info "DRY RUN: I will show what would change and change nothing."
    update_notice

    find_dirs
    [ "$DRY" = 1 ] || check_pi5_usb_hat
    [ -f "$CONFIG_DIR/acepro.cfg" ] && existing=1

    if [ "$MODE" = "update" ] || [ "$existing" = 1 ]; then
        local saved; saved="$(kv_get "$(CONF_FILE)" PROFILE || true)"
        if [ "$existing" = 1 ]; then
            if [ "$MODE" = "update" ] || ask_yn "An ACE Pro install was found. Update it and keep your settings?" Y "no starts a fresh install; your current files are saved first."; then
                UPDATING=1
            fi
        else
            die_with_fix "there is no ACE install to update in $CONFIG_DIR" "run   ./installer.sh   to install first."
        fi
        if [ "$UPDATING" = 1 ]; then
            PROFILE="${saved:-}"
            if [ -z "$PROFILE" ]; then
                print_info "I do not know which software this install was made for."
                choose_profile
            else
                print_info "Profile from your last install: $PROFILE"
            fi
            ACE_COUNT="$(cfg_get "$CONFIG_DIR/acepro_setting.cfg" ace ace_count)"; ACE_COUNT="${ACE_COUNT:-1}"
        fi
    fi

    if [ "$UPDATING" = 0 ]; then
        choose_profile
        load_profile "$PROFILE"
        print_success "Profile: $PROFILE_NAME"
        ask_hardware
    else
        load_profile "$PROFILE"
        print_success "Profile: $PROFILE_NAME"
        local fl="$INSTALL_HOME/fluidd"
        if [ -d "$fl" ] && ask_yn "Also refresh the Fluidd ACE panel?" N "only needed if the panel changed."; then WANT_FLUIDD=1; FLUIDD_DIR="$fl"; fi
        [ -d "$INSTALL_HOME/KlipperScreen/panels" ] && WANT_KS=1
        if [ "$PROFILE" = "saf" ]; then
            if [ -n "$(hooks_included_by)" ]; then HOOKS_INCLUDE=present
            elif [ -f "$CONFIG_DIR/$HOOKS_FILE" ]; then
                HOOKS_INCLUDE=manual
                warn_later "$HOOKS_FILE exists but no file includes it, so the Simple AF hooks do not run. Add [include $HOOKS_FILE] to printer.cfg."
            else
                ask_hooks_include
            fi
        fi
    fi
    [ "$PROFILE" = "kalico" ] || [ "$PROFILE" = "saf" ] || true

    print_header "6 of 7 · What will change"
    stage_files
    echo "Backup of everything that changes:  $BACKUP_ROOT/<date>   (undo: ./installer.sh --undo)"
    echo
    show_plan
    echo
    if ! check_overlay; then
        die_with_fix "the new files would add the problems shown above" "tell me about them with   ./installer.sh --support-bundle"
    fi
    if [ "$DRY" = 1 ]; then
        echo; print_success "Dry run finished. Nothing was changed."
        return 0
    fi
    ask_yn "Continue?" Y || { print_info "Cancelled. Nothing was changed."; return 0; }

    print_header "7 of 7 · Installing"
    BACKUP_DIR="$BACKUP_ROOT/$(timestamp)"
    mkdir -p "$BACKUP_DIR" && : > "$BACKUP_DIR/manifest.txt"
    echo "$VERSION" > "$BACKUP_DIR/installer-version.txt"
    print_success "Backup folder: $BACKUP_DIR"

    link_driver
    remove_old_ace_dashboard
    install_python_packages
    apply_stage
    ensure_include_in_printer_cfg
    [ "$HAVE_CUTTER" = 1 ] && ensure_force_move
    [ "$WANT_CUTCAL" = 1 ] && ensure_include_line "[include cut_calibrate.cfg]"
    [ "$SAF_HOOKS" = "yes" ] && [ "$HOOKS_INCLUDE" = "auto" ] && [ -f "$CONFIG_DIR/$HOOKS_FILE" ] && ensure_include_line "[include $HOOKS_FILE]"
    [ "$WANT_SPOOLMAN" = 1 ] && print_info "spoolman_logic.cfg was copied. To use it, uncomment #[include spoolman_logic.cfg] in acepro.cfg."
    [ "$WANT_FLUIDD" = 1 ] && install_fluidd_panel "$FLUIDD_DIR"
    [ "$WANT_KS" = 1 ] && setup_klipperscreen
    [ -f "$(CONF_FILE)" ] && backup_path "$(CONF_FILE)" || echo "NEW $(CONF_FILE)" >> "$BACKUP_DIR/manifest.txt"
    save_answers

    local stale; stale="$(stale_backup_links)"
    [ -n "$stale" ] && warn_later "Old backup links sit in Klipper's extras folder (ace_backup_*). They are harmless; ./installer.sh --repair removes them."

    restart_and_selftest
    final_steps
}

# ============================================================================
# Modes: check / repair / undo / support bundle
# ============================================================================

do_check() {
    local bad=0 py f x state
    find_dirs
    local saved; saved="$(kv_get "$(CONF_FILE)" PROFILE || true)"
    PROFILE="${saved:-$(detect_profile)}"
    load_profile "$PROFILE"
    echo -e "${BLUE}ACE Pro check${NC}   profile: $PROFILE_NAME${saved:+ (from your last install)}   installer v$VERSION"
    local inst; inst="$(kv_get "$(CONF_FILE)" VERSION || true)"
    [ -n "$inst" ] && [ "$inst" != "$VERSION" ] && print_warning "Installed with v$inst, this download is v$VERSION. Run ./installer.sh --update."
    for f in acepro.cfg acepro_setting.cfg acepro_macros.cfg acepro_printer_macros.cfg; do
        [ -f "$CONFIG_DIR/$f" ] && print_success "$f present" || { print_error "$f is missing"; bad=1; }
    done
    include_present && print_success "printer.cfg includes acepro.cfg" || { print_error "printer.cfg does not include acepro.cfg"; bad=1; }
    if [ "$PROFILE" = "saf" ] && [ -f "$CONFIG_DIR/$HOOKS_FILE" ]; then
        [ -n "$(hooks_included_by)" ] && print_success "$HOOKS_FILE is included" || print_warning "$HOOKS_FILE exists but no file includes it: the Simple AF hooks do not run. Add [include $HOOKS_FILE] to printer.cfg."
    fi
    x="$KLIPPER_DIR/klippy/extras"
    for f in ace temperature_ace.py virtual_pins.py; do
        if [ -e "$x/$f" ]; then print_success "$f in Klipper's extras folder"
        elif is_symlink "$x/$f"; then print_error "$x/$f is a broken link"; bad=1
        else print_error "$x/$f is missing"; bad=1; fi
    done
    [ -n "$(stale_backup_links)" ] && print_warning "Old ace_backup_* links in the extras folder (harmless; --repair removes them)."
    py="$(klippy_python)"
    echo; echo "Config check:"
    "$py" "$VALIDATOR" "$CONFIG_DIR/printer.cfg" --profile "$PROFILE" | sed 's/^/  /'
    [ "${PIPESTATUS[0]}" -eq 0 ] || bad=1
    if command -v curl >/dev/null 2>&1; then
        state="$(klippy_state)"; echo; [ -n "$state" ] && print_info "Klipper state: $state" || print_info "Moonraker is not answering on $MOONRAKER_URL"
    fi
    echo; [ "$bad" = 0 ] && print_success "No problems found." || print_error "Problems found (see above)."
    return $bad
}

do_repair() {
    find_dirs
    local saved; saved="$(kv_get "$(CONF_FILE)" PROFILE || true)"
    PROFILE="${saved:-$(detect_profile)}"
    load_profile "$PROFILE"
    print_info "Repair for profile: $PROFILE_NAME"
    BACKUP_DIR="$BACKUP_ROOT/$(timestamp)-repair"
    mkdir -p "$BACKUP_DIR" && : > "$BACKUP_DIR/manifest.txt"
    link_driver
    local s
    for s in $(stale_backup_links); do
        if is_symlink "$s" && ask_yn "Remove the old backup link $(basename "$s") from Klipper's extras folder?" Y; then
            echo "LINK $s $(readlink "$s")" >> "$BACKUP_DIR/manifest.txt"; rm -f "$s"; print_success "Removed $(basename "$s")"
        fi
    done
    include_present || ensure_include_in_printer_cfg
    # restore files that went missing (never overwrite files that are there)
    STAGE="$(mktemp -d)"
    local f
    for f in acepro.cfg acepro_setting.cfg acepro_macros.cfg acepro_printer_macros.cfg; do
        if [ ! -f "$CONFIG_DIR/$f" ]; then cp "$SCRIPT_DIR/config/$f" "$CONFIG_DIR/$f"; echo "NEW $CONFIG_DIR/$f" >> "$BACKUP_DIR/manifest.txt"; print_warning "$f was missing; restored the default (check your settings)"; fi
    done
    echo
    do_check
}

do_undo() {
    local dir="${1:-}" line kind a b
    [ -n "$dir" ] || dir="$(ls -d "$BACKUP_ROOT"/*/ 2>/dev/null | sort | tail -1)"
    dir="${dir%/}"
    [ -n "$dir" ] && [ -f "$dir/manifest.txt" ] || die_with_fix "there is no backup to restore in $BACKUP_ROOT" "backups are made by ./installer.sh before it changes anything"
    echo "Restoring from: $dir"
    sed 's/^/  /' "$dir/manifest.txt"
    [ "$DRY" = 1 ] && { print_info "Dry run: nothing restored."; return 0; }
    ask_yn "Put these files back?" Y || { print_info "Cancelled."; return 0; }
    # undo in reverse order
    while IFS= read -r line; do
        kind="${line%% *}"; a="${line#* }"
        case "$kind" in
            MOD)  mkdir -p "$(dirname "$a")"; rm -rf "$a"; cp -a "$dir/files$a" "$a" && print_success "Restored $a" ;;
            NEW)  rm -rf "$a" && print_success "Removed $a (it was new)" ;;
            LINK) b="${a#* }"; a="${a%% *}"; rm -f "$a"; [ "$b" != "-" ] && ln -s "$b" "$a"; print_success "Link $a put back" ;;
            FLUIDD) b="${a#* }"; a="${a%% *}"; if [ -d "$b" ]; then rm -rf "$a" && cp -a "$b" "$a" && print_success "Fluidd restored from $b"; fi ;;
        esac
    done < <(tac "$dir/manifest.txt")
    print_success "Done. Restart Klipper: sudo systemctl restart klipper"
}

do_support_bundle() {
    find_dirs
    local out="$INSTALL_HOME/acepro-support-$(timestamp)" py
    mkdir -p "$out"
    py="$(klippy_python)"
    {
        echo "installer: v$VERSION"; echo "date: $(date)"; echo "kernel: $(uname -a)"
        echo "python: $($py --version 2>&1)"
        echo "profile (saved): $(kv_get "$(CONF_FILE)" PROFILE || true)  (detected: $(detect_profile))"
        echo "repo: $(git -C "$SCRIPT_DIR" log -1 --oneline 2>/dev/null)"
        echo; echo "--- klippy/extras ace links"; ls -la "$KLIPPER_DIR/klippy/extras" 2>/dev/null | grep -E 'ace|virtual_pins'
        echo; echo "--- USB"; lsusb 2>/dev/null; ls -la /dev/serial/by-id 2>/dev/null
        echo; echo "--- config check"; "$py" "$VALIDATOR" "$CONFIG_DIR/printer.cfg" --profile "$(kv_get "$(CONF_FILE)" PROFILE || detect_profile)" 2>&1
    } > "$out/info.txt"
    local f
    for f in "$CONFIG_DIR"/acepro*.cfg "$CONFIG_DIR"/acepro-install.conf "$CONFIG_DIR/printer.cfg" "$CONFIG_DIR/saved_variables.cfg"; do
        [ -f "$f" ] && sed -E 's/((password|passwd|token|api[_-]?key|secret|private[_-]?key)[A-Za-z_]*[[:space:]]*[:=]).*/\1 REMOVED/I' "$f" > "$out/$(basename "$f")"
    done
    local log="$INSTALL_HOME/printer_data/logs/klippy.log"
    [ -f "$log" ] && tail -n 3000 "$log" > "$out/klippy.log.tail"
    tar -czf "$out.tar.gz" -C "$(dirname "$out")" "$(basename "$out")" && rm -rf "$out"
    print_success "Support bundle: $out.tar.gz"
    echo "  It holds your ACE and printer config (passwords and tokens removed), the end of klippy.log and the check results."
    echo "  Look it over before you share it."
}

# ============================================================================
# Entry point
# ============================================================================

usage() { sed -n '/^# \.\/installer\.sh/p' "$0" | sed 's/^# //'; }

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --update) MODE=update ;;
            --check) MODE=check ;;
            --repair|--relink) MODE=repair ;;
            --undo) MODE=undo; if [ "${2:-}" ] && [ "${2:0:2}" != "--" ]; then UNDO_ARG="$2"; shift; fi ;;
            --support-bundle) MODE=bundle ;;
            --dry-run) DRY=1 ;;
            --klipper-dir) KLIPPER_DIR="${2:-}"; shift ;;
            --config-dir) CONFIG_DIR="${2:-}"; shift ;;
            --version) echo "$VERSION"; exit 0 ;;
            -h|--help) usage; exit 0 ;;
            *) echo "Unknown option: $1"; usage; exit 64 ;;
        esac
        shift
    done
}

main() {
    parse_args "$@"
    command -v python3 >/dev/null 2>&1 || die_with_fix "python3 is not installed" "sudo apt-get install -y python3"
    case "$MODE" in
        install|update) do_install ;;
        check) do_check ;;
        repair) do_repair ;;
        undo) do_undo "$UNDO_ARG" ;;
        bundle) do_support_bundle ;;
    esac
}

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
