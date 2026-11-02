#!/usr/bin/env bash
# Full snapshot of everything the ACE Pro installer can change, and a one-command restore.
#
#   tools/full_backup.sh                 make a snapshot   (changes nothing on the printer)
#   tools/full_backup.sh --list          show your snapshots
#   tools/full_backup.sh --restore       put the newest snapshot back
#   tools/full_backup.sh --restore DIR   put a specific snapshot back
#
# What is saved (in ~/acepro-fullbackup/<date>/):
#   config.tar.gz   your whole printer_data/config folder (printer.cfg, acepro*.cfg, saved_variables.cfg ...)
#   repo.tar.gz     the ~/acepro-any-klipper folder (the driver code Klipper is running right now)
#   extras.tar.gz   the ACE links/files inside Klipper's klippy/extras folder
#   fluidd.tar.gz   your Fluidd folder (only if there is one)
#   panels.tar.gz   the KlipperScreen ACE panel link (only if there is one)
#   INFO.txt        versions, what was found
# Restore never deletes: the files it replaces are moved next to the originals as *.before-restore-<date>.
set -u
HOME_DIR="${ACE_INSTALL_HOME:-$HOME}"
CONFIG_DIR="${ACE_CONFIG_DIR:-$HOME_DIR/printer_data/config}"
KLIPPER_DIR="${ACE_KLIPPER_DIR:-$HOME_DIR/klipper}"
REPO_DIR="${ACE_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="$HOME_DIR/acepro-fullbackup"
EXTRAS="$KLIPPER_DIR/klippy/extras"
PANELS="$HOME_DIR/KlipperScreen/panels"
FLUIDD="$HOME_DIR/fluidd"
TS="$(date +%Y%m%d_%H%M%S)"

say()  { printf '%s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ask()  { local a; [ "${ACE_INSTALLER_TEST:-0}" = 1 ] && return 0; read -r -p "$1 [Y/n] " a || return 1; case "${a:-y}" in y|Y|yes) return 0 ;; *) return 1 ;; esac; }

ace_extras() { # names in klippy/extras that belong to the ACE install
    [ -d "$EXTRAS" ] || return 0
    find "$EXTRAS" -maxdepth 1 \( -name 'ace' -o -name 'ace_*' -o -name 'virtual_pins.py' -o -name 'temperature_ace*' \) -printf '%f\n' 2>/dev/null | sort
}

do_backup() {
    local dir="$ROOT/$TS" n
    [ -d "$CONFIG_DIR" ] || die "config folder not found: $CONFIG_DIR"
    mkdir -p "$dir" || die "cannot create $dir"
    say "Saving to $dir"

    tar -czf "$dir/config.tar.gz" -C "$(dirname "$CONFIG_DIR")" "$(basename "$CONFIG_DIR")" || die "config backup failed"
    say "  ok   config folder"

    if [ -d "$REPO_DIR" ]; then
        tar -czf "$dir/repo.tar.gz" -C "$(dirname "$REPO_DIR")" "$(basename "$REPO_DIR")" || die "repo backup failed"
        say "  ok   $(basename "$REPO_DIR") folder (current driver code)"
    fi

    n="$(ace_extras)"
    if [ -n "$n" ]; then
        # shellcheck disable=SC2086
        (cd "$EXTRAS" && tar -czf "$dir/extras.tar.gz" $n) || die "extras backup failed"
        say "  ok   Klipper extras: $(echo $n | tr '\n' ' ')"
    fi

    if [ -d "$FLUIDD" ]; then
        tar -czf "$dir/fluidd.tar.gz" -C "$HOME_DIR" fluidd && say "  ok   Fluidd folder"
    fi
    if [ -d "$PANELS" ] && ls "$PANELS"/acepro* >/dev/null 2>&1; then
        (cd "$PANELS" && tar -czf "$dir/panels.tar.gz" acepro*) && say "  ok   KlipperScreen ACE panel"
    fi

    {
        echo "Snapshot:    $TS"
        echo "Host:        $(hostname 2>/dev/null)"
        echo "Config dir:  $CONFIG_DIR"
        echo "Repo dir:    $REPO_DIR"
        [ -d "$REPO_DIR/.git" ] && { echo "Repo commit: $(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null) ($(git -C "$REPO_DIR" branch --show-current 2>/dev/null))"; echo "Repo version: $(cat "$REPO_DIR/VERSION" 2>/dev/null || echo 'no VERSION file (older download)')"; }
        [ -d "$KLIPPER_DIR/.git" ] && echo "Klipper:     $(git -C "$KLIPPER_DIR" rev-parse --short HEAD 2>/dev/null)"
        echo "Extras:"; (cd "$EXTRAS" 2>/dev/null && for f in $(ace_extras); do ls -ld "$f"; done)
    } > "$dir/INFO.txt"
    ( cd "$dir" && sha256sum ./*.tar.gz > SHA256SUMS )
    say ""
    say "Done. To go back to exactly this state later:"
    say "    $REPO_DIR/tools/full_backup.sh --restore $dir"
    say "(Keep a copy of $dir off the Pi if you can, for example with SFTP.)"
}

do_list() {
    local d
    [ -d "$ROOT" ] || { say "No snapshots yet ($ROOT)."; return 0; }
    for d in "$ROOT"/*/; do
        [ -f "$d/INFO.txt" ] || continue
        printf '%s   %s   %s\n' "$(basename "$d")" "$(du -sh "$d" | cut -f1)" "$(grep -m1 '^Repo commit' "$d/INFO.txt")"
    done
}

move_aside() { # path
    local p="$1"
    if [ -e "$p" ] || [ -L "$p" ]; then mv "$p" "$p.before-restore-$TS" && say "  kept your current $(basename "$p") as $(basename "$p").before-restore-$TS"; fi
}

do_restore() {
    local dir="${1:-}" n
    if [ -z "$dir" ]; then dir="$(ls -d "$ROOT"/*/ 2>/dev/null | sort | tail -1)"; fi
    dir="${dir%/}"
    [ -n "$dir" ] && [ -f "$dir/config.tar.gz" ] || die "no snapshot found. Make one first: tools/full_backup.sh"
    ( cd "$dir" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ) || die "the snapshot files do not match their checksums ($dir). Nothing was changed."
    say "Restoring snapshot $(basename "$dir")"
    sed 's/^/    /' "$dir/INFO.txt"
    say ""
    say "This puts back your config folder, the driver folder, the Klipper ACE links and Fluidd."
    say "Your current versions are not deleted: they are renamed *.before-restore-$TS."
    ask "Restore now?" || { say "Cancelled. Nothing was changed."; return 0; }

    if [ "${ACE_NO_SYSTEMCTL:-0}" != 1 ] && command -v systemctl >/dev/null 2>&1; then sudo systemctl stop klipper 2>/dev/null && say "  stopped Klipper"; fi

    move_aside "$CONFIG_DIR"
    tar -xzf "$dir/config.tar.gz" -C "$(dirname "$CONFIG_DIR")" && say "  restored config folder"

    if [ -f "$dir/repo.tar.gz" ]; then
        move_aside "$REPO_DIR"
        tar -xzf "$dir/repo.tar.gz" -C "$(dirname "$REPO_DIR")" && say "  restored $(basename "$REPO_DIR")"
    fi

    if [ -f "$dir/extras.tar.gz" ]; then
        local keep f; keep="$(tar -tzf "$dir/extras.tar.gz" | sed 's#/.*##' | sort -u)"
        for f in $(ace_extras); do   # ACE entries that were not there at backup time are moved aside
            echo "$keep" | grep -qxF "$f" || move_aside "$EXTRAS/$f"
        done
        for f in $keep; do rm -rf "${EXTRAS:?}/$f"; done
        tar -xzf "$dir/extras.tar.gz" -C "$EXTRAS" && say "  restored Klipper extras links"
    fi

    if [ -f "$dir/fluidd.tar.gz" ]; then
        move_aside "$FLUIDD"
        tar -xzf "$dir/fluidd.tar.gz" -C "$HOME_DIR" && say "  restored Fluidd"
    fi
    if [ -f "$dir/panels.tar.gz" ]; then
        local pf
        for pf in $(tar -tzf "$dir/panels.tar.gz"); do rm -rf "${PANELS:?}/$pf"; done
        tar -xzf "$dir/panels.tar.gz" -C "$PANELS" && say "  restored KlipperScreen ACE panel"
    fi

    if [ "${ACE_NO_SYSTEMCTL:-0}" != 1 ] && command -v systemctl >/dev/null 2>&1; then
        ask "Start Klipper again now?" && sudo systemctl start klipper 2>/dev/null && say "  Klipper started"
    fi
    say ""
    say "Done. Your printer is back as it was at $(basename "$dir")."
}

case "${1:-}" in
    ""|--backup) do_backup ;;
    --list)      do_list ;;
    --restore)   do_restore "${2:-}" ;;
    -h|--help)   sed -n 2,19p "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
    *) die "unknown option: $1 (try --help)" ;;
esac
