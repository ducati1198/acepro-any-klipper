#!/bin/bash
# =============================================================================
# Pin a working kernel on a Raspberry Pi 5 with a PCIe USB HAT
# =============================================================================
# Problem: on a Pi 5 with a PCIe to USB HAT (Waveshare, VIA VL805 chip) the newer
# 6.12.x kernels fail to start the HAT's USB controller:
#     xhci_hcd ...: can't setup: -12
# No USB device behind the HAT shows up, so Klipper cannot find the ACE units, the
# toolhead MCU or the expander board ("'NoneType' object has no attribute 'send'").
# Upstream: https://github.com/raspberrypi/linux/issues/7715 (still open when this
# was written). Reported broken: 6.12.109.  Reported working: 6.12.75 and 6.12.96.
#
# What this script does:
#   1. installs the older kernel package if it is not on the system yet
#   2. copies its kernel and initramfs next to config.txt
#   3. points config.txt (Pi 5 only) at them, then syncs (an unflushed write to the
#      FAT boot partition is lost on reboot)
#   4. holds the kernel meta packages so "apt upgrade" does not move you forward
#
# Usage (run on the Pi, as root):
#   sudo bash tools/pin-pi5-kernel.sh --check            # only look, change nothing
#   sudo bash tools/pin-pi5-kernel.sh                    # pin 6.12.96 (default)
#   sudo bash tools/pin-pi5-kernel.sh --kernel 6.12.75   # pin another version
#   sudo bash tools/pin-pi5-kernel.sh --unpin            # go back to the newest kernel
#
# Undo by hand: delete the block between "acepro-kernel-pin" in
# /boot/firmware/config.txt, then reboot.
# =============================================================================

set -u

# Paths can be overridden, which is also how the script is tested.
BOOT_DIR="${BOOT_DIR:-/boot}"                 # holds vmlinuz-<release> and initrd.img-<release>
FW_DIR="${FW_DIR:-/boot/firmware}"            # holds config.txt
[ -f "$FW_DIR/config.txt" ] || { [ -f /boot/config.txt ] && FW_DIR=/boot; }
MOD_DIR="${MOD_DIR:-/lib/modules}"
CONFIG="$FW_DIR/config.txt"
MARK_BEGIN="# >>> acepro-kernel-pin (managed by tools/pin-pi5-kernel.sh, remove with --unpin)"
MARK_END="# <<< acepro-kernel-pin"
PIN_KERNEL_FILE="kernel_pinned.img"
PIN_INITRD_FILE="initrd_pinned.img"
SUFFIX="+rpt-rpi-2712"
META_PKGS="linux-image-rpi-2712 linux-image-rpi-v8 linux-headers-rpi-2712 linux-headers-rpi-v8"

KERNEL_WANTED="6.12.96"
MODE="pin"
FORCE=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}OK${NC}   $*"; }
warn() { echo -e "${YELLOW}WARN${NC} $*"; }
die()  { echo -e "${RED}ERROR${NC} $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --check)  MODE="check" ;;
        --unpin)  MODE="unpin" ;;
        --kernel) shift; KERNEL_WANTED="${1:-}"; [ -n "$KERNEL_WANTED" ] || die "--kernel needs a version, e.g. 6.12.96" ;;
        --force)  FORCE=1 ;;
        -h|--help) sed -n 2,34p "$0"; exit 0 ;;
        *) die "Unknown option: $1 (try --help)" ;;
    esac
    shift
done

is_pi5() { grep -qa "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null; }

need_root() {
    [ "$(id -u)" -eq 0 ] || [ "${ACEPRO_TEST:-0}" = "1" ] || die "Run this as root: sudo bash $0 $*"
}

kernel_log() {
    { dmesg 2>/dev/null; journalctl -k --no-pager 2>/dev/null; } | grep -i "xhci" || true
}

installed_releases() {
    ls "$MOD_DIR" 2>/dev/null | grep -E "rpi-2712$" | sort -V
}

pin_active() { grep -qF "$MARK_BEGIN" "$CONFIG" 2>/dev/null; }

strip_block() {
    # Remove an existing pin block from config.txt (if any), writing to a temp file.
    awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
        $0==b {skip=1; next}
        skip && $0==e {skip=0; next}
        !skip {print}' "$CONFIG" > "$CONFIG.new" || die "could not rewrite $CONFIG"
}

write_config() {
    [ -s "$CONFIG.new" ] || die "refusing to write an empty config.txt"
    cp -a "$CONFIG" "$CONFIG.bak_acepro_$(date +%Y%m%d_%H%M%S)"
    cat "$CONFIG.new" > "$CONFIG"
    rm -f "$CONFIG.new"
    sync
}

hold_meta() {
    [ "${NO_APT:-0}" = "1" ] && return 0
    for p in $META_PKGS; do
        if dpkg -s "$p" >/dev/null 2>&1; then apt-mark "$1" "$p" >/dev/null 2>&1 && ok "apt-mark $1 $p"; fi
    done
}

# --------------------------------------------------------------------------- check
do_check() {
    echo "Running kernel : $(uname -r)"
    if is_pi5; then ok "Raspberry Pi 5 detected"; else warn "This does not look like a Pi 5 (this script is for Pi 5 only)"; fi
    echo "Installed Pi 5 kernels:"; installed_releases | sed 's/^/   /'
    local lines; lines="$(kernel_log)"
    if echo "$lines" | grep -qiE "can't setup|probe.*failed|-12"; then
        warn "xhci errors in the kernel log: the USB HAT controller failed to start"
        echo "$lines" | grep -iE "can't setup|probe.*failed|-12" | head -3 | sed 's/^/   /'
    elif [ -n "$lines" ]; then ok "xhci present, no setup errors in the kernel log"
    else warn "no xhci lines in the kernel log (no USB 3 controller found at all?)"; fi
    if pin_active; then ok "kernel pin is active in $CONFIG"; else echo "No kernel pin in $CONFIG"; fi
    echo "Held packages:"; apt-mark showhold 2>/dev/null | grep -E "linux-(image|headers)" | sed 's/^/   /'
    return 0
}

# --------------------------------------------------------------------------- unpin
do_unpin() {
    need_root --unpin
    [ -f "$CONFIG" ] || die "$CONFIG not found"
    if pin_active; then
        strip_block; write_config; ok "pin block removed from $CONFIG"
    else
        echo "No pin block in $CONFIG"
    fi
    rm -f "$FW_DIR/$PIN_KERNEL_FILE" "$FW_DIR/$PIN_INITRD_FILE"; sync
    hold_meta unhold
    echo "Reboot to use the newest kernel again:  sudo reboot"
}

# --------------------------------------------------------------------------- pin
find_release() {
    # newest installed Pi 5 kernel whose release starts with the wanted version
    installed_releases | grep -E "^${KERNEL_WANTED//./\\.}[.+-]" | tail -1
}

do_pin() {
    need_root
    [ -f "$CONFIG" ] || die "$CONFIG not found (is this Raspberry Pi OS?)"
    if ! is_pi5 && [ "$FORCE" -ne 1 ] && [ "${ACEPRO_TEST:-0}" != "1" ]; then
        die "This is not a Pi 5. Nothing to do (use --force to override)."
    fi

    local rel; rel="$(find_release)"
    if [ -z "$rel" ]; then
        local pkg="linux-image-${KERNEL_WANTED}${SUFFIX}"
        echo "Kernel $KERNEL_WANTED is not installed. Installing $pkg ..."
        if [ "${NO_APT:-0}" = "1" ]; then die "NO_APT=1 and the kernel is not installed"; fi
        apt-get update -qq || warn "apt-get update failed, trying with the cached package list"
        if ! apt-get install -y "$pkg"; then
            echo
            echo "That package is not available from the apt sources. Kernels apt offers:"
            apt-cache search --names-only '^linux-image-6\.12\..*rpi-2712$' | sort -V | sed 's/ - .*//; s/^/   /'
            die "Pick one of those with:  sudo bash $0 --kernel <version>   (for example 6.12.75)"
        fi
        rel="$(find_release)"
        [ -n "$rel" ] || die "Installed $pkg but no matching directory appeared in $MOD_DIR"
    fi
    ok "using kernel $rel"

    local img="$BOOT_DIR/vmlinuz-$rel" ird="$BOOT_DIR/initrd.img-$rel"
    [ -f "$img" ] || die "$img not found: the kernel package did not install its image"

    cp "$img" "$FW_DIR/$PIN_KERNEL_FILE" || die "could not copy the kernel to $FW_DIR"
    cmp -s "$img" "$FW_DIR/$PIN_KERNEL_FILE" || die "kernel copy does not match, boot partition full?"
    local use_initrd=0
    if [ -f "$ird" ]; then
        cp "$ird" "$FW_DIR/$PIN_INITRD_FILE" || die "could not copy the initramfs to $FW_DIR"
        cmp -s "$ird" "$FW_DIR/$PIN_INITRD_FILE" || die "initramfs copy does not match, boot partition full?"
        use_initrd=1
    else
        warn "no initramfs for $rel; booting without one (fine on Raspberry Pi OS images)"
    fi
    sync

    strip_block
    {
        echo ""
        echo "$MARK_BEGIN"
        echo "[pi5]"
        echo "kernel=$PIN_KERNEL_FILE"
        if [ "$use_initrd" -eq 1 ]; then
            echo "auto_initramfs=0"
            echo "initramfs $PIN_INITRD_FILE followkernel"
        fi
        echo "[all]"
        echo "$MARK_END"
    } >> "$CONFIG.new"
    write_config
    ok "config.txt now boots $rel on the Pi 5 (backup saved next to it)"

    hold_meta hold
    echo
    echo "Done. Reboot, then check:"
    echo "   sudo reboot"
    echo "   uname -r                      # should show $rel"
    echo "   dmesg | grep -i xhci          # no 'can't setup: -12'"
    echo "   lsusb                         # the ACE units / MCUs are listed again"
}

case "$MODE" in
    check) do_check ;;
    unpin) do_unpin ;;
    pin)   do_pin ;;
esac
