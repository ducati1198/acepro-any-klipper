#!/bin/bash

# =============================================================================
# ACE Pro Klipper Driver - Interactive Installer
# =============================================================================
# This script performs the necessary installation steps to set up the ACE Pro
# driver for Klipper, including configuration file setup and symlinks.
#
# Compatible with: Raspberry Pi OS, Debian, Ubuntu
# Usage: ./installer.sh
#
# =============================================================================

set -u  # Exit on undefined variables

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory (where this script is located)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Resolve installation user/home for defaults (works when run via sudo).
INSTALL_USER="${SUDO_USER:-$(id -un)}"
INSTALL_HOME="$(getent passwd "$INSTALL_USER" 2>/dev/null | cut -d: -f6 || true)"
if [ -z "$INSTALL_HOME" ]; then
    INSTALL_HOME="$HOME"
fi

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_info() {
    echo -e "${BLUE}ℹ ${1}${NC}"
}

print_success() {
    echo -e "${GREEN}✓ ${1}${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ ${1}${NC}"
}

print_error() {
    echo -e "${RED}✗ ${1}${NC}"
}

# Yes/No prompt
prompt_yes_no() {
    local prompt="$1"
    local response
    while true; do
        read -p "$(echo -e ${BLUE}${prompt}${NC} [y/N]: )" response
        case "$response" in
            [yY][eE][sS]|[yY]) return 0 ;;
            [nN][oO]|[nN]|"") return 1 ;;
            *) echo "Please answer y or n" ;;
        esac
    done
}

# Prompt for input with default
prompt_input() {
    local prompt="$1"
    local default="$2"
    local response
    read -p "$(echo -e ${BLUE}${prompt}${NC} [${default}]: )" response
    echo "${response:-$default}"
}

# Create backup with timestamp
backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        local timestamp=$(date +"%Y%m%d_%H%M%S")
        local backup="${file}.backup_${timestamp}"
        cp "$file" "$backup"
        print_success "Backed up: $file → $backup"
        return 0
    fi
    return 1
}

# Remove a symlink if it exists and show what it pointed to
remove_symlink_if_exists() {
    local path="$1"
    if is_symlink "$path"; then
        local target=$(readlink "$path")
        rm -f "$path"
        print_info "Removed symlink: $path (was pointing to: $target)"
        return 0
    fi
    return 1
}

# Check if path is a symlink
is_symlink() {
    [ -L "$1" ]
}

# Add a line to printer.cfg if not already present (insert at the top)
ensure_include_in_printer_cfg() {
    local printer_cfg="$1"
    local include_line="[include acepro.cfg]"

    if [ ! -f "$printer_cfg" ]; then
        print_warning "printer.cfg not found at $printer_cfg. Creating a new one with include line."
        echo "$include_line" > "$printer_cfg"
        print_success "Created $printer_cfg with include line."
        return 0
    fi

    # Check if include line already exists (with optional spaces)
    if grep -qE '^\s*\[include\s+acepro\.cfg\]' "$printer_cfg"; then
        print_success "printer.cfg already includes acepro.cfg"
        return 0
    fi

    # Ask user if they want to add it
    if prompt_yes_no "Add '[include acepro.cfg]' at the top of printer.cfg?"; then
        # Backup before modifying
        backup_file "$printer_cfg"

        # Create a temporary file with the include line first, then the original content
        local tmpfile
        tmpfile=$(mktemp)
        echo "$include_line" > "$tmpfile"
        echo "" >> "$tmpfile"   # optional blank line for readability
        cat "$printer_cfg" >> "$tmpfile"
        mv "$tmpfile" "$printer_cfg"
        print_success "Added '$include_line' at the top of $printer_cfg"
    else
        print_warning "Skipped adding include line. You must manually add it later."
    fi
}

# Add a KlipperScreen menu entry (handles user-editable section vs auto-generated marker)
ensure_menu_entry() {
    local conf="$1"
    local header="$2"
    local block="$3"
    local label="$4"

    # Extract user-editable section (lines before the #~# auto-generated marker)
    local user_section
    user_section=$(sed '/^#~# --- Do not edit/,$d' "$conf" 2>/dev/null || cat "$conf" 2>/dev/null || true)

    if echo "$user_section" | grep -qF "$header"; then
        print_success "KlipperScreen.conf: $label entry already present"
        return 0
    fi

    print_info "Adding $label entry to $conf"
    local tmpfile
    tmpfile=$(mktemp)

    if grep -q '^#~# --- Do not edit' "$conf" 2>/dev/null; then
        # Insert the block just before the auto-generated marker
        awk -v block="$block" '
            /^#~# --- Do not edit/ && !done {
                print block; print ""; done=1
            }
            { print }
        ' "$conf" > "$tmpfile" && mv "$tmpfile" "$conf"
    else
        # No marker — append at end of file
        printf '\n%s\n' "$block" >> "$conf"
    fi
    print_success "KlipperScreen.conf: added $label entry"
}

# Ensure the ACE Pro menu entry exists in main and print menus
ensure_klipperscreen_acepro_menu() {
    local conf="$1"
    local entry_block_main='[menu __main acepro]\nname: ACE Pro\nicon: settings\npanel: acepro'
    local entry_block_print='[menu __print acepro]\nname: ACE Pro\nicon: settings\npanel: acepro'

    ensure_menu_entry "$conf" "[menu __main acepro]" "$entry_block_main" "ACE Pro (main menu)"
    ensure_menu_entry "$conf" "[menu __print acepro]" "$entry_block_print" "ACE Pro (print menu)"
}

# Ensure [ace_status] section exists in moonraker.conf (create file if missing)
ensure_moonraker_ace_status() {
    local conf="$1"

    if [ -f "$conf" ] && grep -qi '^[[:space:]]*\[ace_status\]' "$conf"; then
        print_success "moonraker.conf: [ace_status] already present"
        return 0
    fi

    mkdir -p "$(dirname "$conf")"
    if [ ! -f "$conf" ]; then
        printf '# Moonraker configuration\n\n' > "$conf"
        print_warning "Created new moonraker.conf at $conf"
    fi

    printf '\n# ACE status extension\n[ace_status]\n' >> "$conf"
    print_success "Added [ace_status] to $conf"
}

# Ensure font_size = small is set in the user-editable section of KlipperScreen.conf
# Handles missing file, missing [main] section, wrong value, and #~# auto-generated block.
ensure_klipperscreen_font_size() {
    local conf="$1"

    if [ ! -f "$conf" ]; then
        printf '[main]\nfont_size = small\n' > "$conf"
        print_success "Created $conf with font_size = small"
        return 0
    fi

    # Extract user-editable section (lines before the #~# auto-generated marker)
    local user_section
    user_section=$(sed '/^#~# --- Do not edit/,$d' "$conf")

    # Already correct?
    if echo "$user_section" | grep -qiE '^[[:space:]]*font_size[[:space:]]*=[[:space:]]*small[[:space:]]*$'; then
        print_success "KlipperScreen.conf: font_size = small is already configured"
        return 0
    fi

    print_info "Configuring font_size = small in $conf"
    local tmpfile
    tmpfile=$(mktemp)

    if echo "$user_section" | grep -qiE '^[[:space:]]*font_size[[:space:]]*='; then
        # font_size exists with a different value — update first occurrence before #~# block
        awk '
            /^#~# --- Do not edit/ { in_auto=1 }
            !in_auto && /^[[:space:]]*font_size[[:space:]]*=/ && !replaced {
                print "font_size = small"; replaced=1; next
            }
            { print }
        ' "$conf" > "$tmpfile" && mv "$tmpfile" "$conf"
        print_success "KlipperScreen.conf: updated font_size to small"

    elif echo "$user_section" | grep -q '^\[main\]'; then
        # [main] exists in user section but no font_size — insert after first [main]
        awk '
            /^#~# --- Do not edit/ { in_auto=1 }
            !in_auto && /^\[main\]$/ && !done {
                print; print "font_size = small"; done=1; next
            }
            { print }
        ' "$conf" > "$tmpfile" && mv "$tmpfile" "$conf"
        print_success "KlipperScreen.conf: added font_size = small under [main]"

    else
        # No [main] in user section — insert block before #~# marker or prepend
        if grep -q '^#~# --- Do not edit' "$conf"; then
            awk '
                /^#~# --- Do not edit/ && !done {
                    print "[main]"; print "font_size = small"; print ""; done=1
                }
                { print }
            ' "$conf" > "$tmpfile" && mv "$tmpfile" "$conf"
        else
            { printf '[main]\nfont_size = small\n\n'; cat "$conf"; } > "$tmpfile" && mv "$tmpfile" "$conf"
        fi
        print_success "KlipperScreen.conf: added [main] section with font_size = small"
    fi
}

# Copy an optional config file next to the other ACE configs.
# Missing -> copy. Identical -> nothing. Different -> ask, back up, replace.
install_optional_cfg() {
    local source="$1"
    local target="$2"
    local label="$3"

    if [ ! -f "$source" ]; then
        print_warning "$label not found in the repository: $source"
        return 1
    fi
    if [ -f "$target" ] && cmp -s "$source" "$target"; then
        print_success "$label already up to date"
        return 0
    fi
    if [ -e "$target" ] || is_symlink "$target"; then
        print_warning "$label already exists and differs"
        if ! prompt_yes_no "Back up and replace $label?"; then
            print_info "Kept your $label"
            return 0
        fi
        backup_file "$target"
        is_symlink "$target" && remove_symlink_if_exists "$target"
    fi
    cp "$source" "$target"
    print_success "Copied: $source → $target"
}

# Add a line like "[include cut_calibrate.cfg]" right after the acepro include.
ensure_include_line() {
    local printer_cfg="$1"
    local include_line="$2"

    [ -f "$printer_cfg" ] || { print_warning "printer.cfg not found: $printer_cfg"; return 1; }
    if grep -qF "$include_line" "$printer_cfg"; then
        print_success "printer.cfg already has $include_line"
        return 0
    fi
    backup_file "$printer_cfg"
    local tmpfile
    tmpfile=$(mktemp)
    awk -v line="$include_line" '
        { print }
        /^[[:space:]]*\[include[[:space:]]+acepro\.cfg\]/ && !done { print line; done=1 }
        END { if (!done) print line }
    ' "$printer_cfg" > "$tmpfile" && mv "$tmpfile" "$printer_cfg"
    print_success "Added $include_line to printer.cfg"
}

# CUT_TIP uses FORCE_MOVE, so [force_move] must be enabled.
ensure_force_move() {
    local printer_cfg="$1"

    [ -f "$printer_cfg" ] || { print_warning "printer.cfg not found: $printer_cfg"; return 1; }
    if grep -qE '^[[:space:]]*\[force_move\]' "$printer_cfg"; then
        if grep -qiE '^[[:space:]]*enable_force_move[[:space:]]*:[[:space:]]*true' "$printer_cfg"; then
            print_success "printer.cfg: [force_move] already enabled"
        else
            print_warning "printer.cfg has [force_move] but enable_force_move is not True."
            print_info "Set 'enable_force_move: True' in that section (CUT_TIP needs it)."
        fi
        return 0
    fi
    backup_file "$printer_cfg"
    printf '\n[force_move]\nenable_force_move: True\n' >> "$printer_cfg"
    print_success "Added [force_move] enable_force_move: True to printer.cfg"
}

# Install the Fluidd build that has the ACE Pro card and the spool picker.
# Keeps a backup, keeps your Fluidd settings (config.json) and your ACE dashboard links.
install_fluidd_panel() {
    local fluidd_dir="$1"
    local zip="$SCRIPT_DIR/fluidd/fluidd-v1.37.7-acepro.zip"
    local sum="$zip.sha256"

    if [ ! -f "$zip" ]; then
        print_error "Fluidd build not found: $zip"
        return 1
    fi
    if [ -f "$sum" ]; then
        if (cd "$SCRIPT_DIR/fluidd" && sha256sum -c "$(basename "$sum")" >/dev/null 2>&1); then
            print_success "Checksum OK"
        else
            print_error "Checksum of $zip does not match. Not installing."
            return 1
        fi
    fi
    if [ ! -d "$fluidd_dir" ]; then
        print_warning "Fluidd directory not found: $fluidd_dir"
        print_info "Install Fluidd first (for example with KIAUH), then run this installer again."
        return 1
    fi

    local backup="${fluidd_dir}_backup_$(date +"%Y%m%d_%H%M%S")"
    cp -a "$fluidd_dir" "$backup" && print_success "Backed up Fluidd → $backup"

    # Old hashed files would just pile up
    rm -rf "$fluidd_dir/assets"

    if command -v unzip >/dev/null 2>&1; then
        unzip -qo "$zip" -x config.json -d "$fluidd_dir"
    else
        python3 - "$zip" "$fluidd_dir" <<'PYZIP'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
for n in z.namelist():
    if n != "config.json":
        z.extract(n, sys.argv[2])
PYZIP
    fi
    # A fresh Fluidd has no config.json yet - use the one from the build
    [ -f "$fluidd_dir/config.json" ] || python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extract('config.json', sys.argv[2])" "$zip" "$fluidd_dir"
    chmod -R a+rX "$fluidd_dir" 2>/dev/null || true

    if grep -rlq "Choose ACE spools" "$fluidd_dir/assets" 2>/dev/null; then
        print_success "Fluidd ACE panel installed"
    else
        print_error "Could not find the ACE panel in $fluidd_dir/assets - restoring backup"
        rm -rf "$fluidd_dir" && cp -a "$backup" "$fluidd_dir"
        return 1
    fi
    if grep -qE '^\[update_manager[[:space:]]+fluidd\]' "$CONFIG_DIR/moonraker.conf" 2>/dev/null; then
        print_warning "moonraker.conf has [update_manager fluidd]: updating Fluidd there replaces this build."
        print_info "Run this installer again after a Fluidd update, or remove that section."
    fi
    print_info "Hard-refresh the browser (Ctrl/Cmd+Shift+R) to load it."
}

# Create or replace symlink
create_or_replace_symlink() {
    local source="$1"
    local target="$2"
    local description="$3"
    
    if [ ! -e "$source" ]; then
        print_error "$source does not exist, skipping symlink"
        return 1
    fi
    
    if [ -e "$target" ] || is_symlink "$target"; then
        if is_symlink "$target"; then
            print_warning "Symlink already exists: $target"
            local current_target=$(readlink "$target")
            print_info "  → Currently points to: $current_target"
        else
            print_warning "File/directory already exists: $target"
        fi
        
        if prompt_yes_no "Replace it?"; then
            rm -f "$target"
            ln -sf "$source" "$target"
            print_success "Symlink created: $target → $source"
            return 0
        else
            print_info "Skipped symlink for $description"
            return 1
        fi
    else
        # Target doesn't exist, create symlink
        mkdir -p "$(dirname "$target")"
        ln -sf "$source" "$target"
        print_success "Symlink created: $target → $source"
        return 0
    fi
}

# ============================================================================
# Main Installation
# ============================================================================

main() {
    print_header "ACE Pro Klipper Driver - Interactive Installer"
    
    # Track backup files for final instructions
    ACE_CONFIG_BACKUP=""
    ACE_MACROS_BACKUP=""
    PRINTER_GENERIC_MACROS_BACKUP=""
    MOONRAKER_RESTART_NEEDED=0
    
    # ========================================================================
    # Step 1: Gather user input
    # ========================================================================
    
    print_info "Gathering installation parameters...\n"
    print_info "Installer source directory: $SCRIPT_DIR"
    print_info "Default target user/home: $INSTALL_USER ($INSTALL_HOME)"
    
    # 1.1 - Klipper installation directory
    DEFAULT_KLIPPER_DIR="$INSTALL_HOME/klipper"
    KLIPPER_DIR=$(prompt_input "Klipper installation directory (press ENTER to use default)" "$DEFAULT_KLIPPER_DIR")
    
    if [ ! -d "$KLIPPER_DIR" ]; then
        print_error "Klipper directory not found: $KLIPPER_DIR"
        exit 1
    fi
    print_success "Using Klipper directory: $KLIPPER_DIR"
    
    # 1.2 - Config directory
    DEFAULT_CONFIG_DIR="$INSTALL_HOME/printer_data/config"
    CONFIG_DIR=$(prompt_input "\nKlipper config directory" "$DEFAULT_CONFIG_DIR")
    
    if [ ! -d "$CONFIG_DIR" ]; then
        print_error "Config directory not found: $CONFIG_DIR"
        exit 1
    fi
    print_success "Using config directory: $CONFIG_DIR"
    
    # ========================================================================
    # Step 2: Ask for confirmation
    # ========================================================================
    
    echo ""
    print_header "Installation Summary"
    
    cat << EOF
Script directory:        $SCRIPT_DIR
Klipper directory:       $KLIPPER_DIR
Config directory:        $CONFIG_DIR

Installation steps:
1. Link ace module to Klipper extras
1b. (Optional) Install ACE status Moonraker component + dashboard symlinks
1c. Check the Python packages the driver needs (pyserial, jinja2)
1d. (Optional) Install the Fluidd ACE Pro card + spool picker
2. Ensure printer.cfg includes acepro.cfg (at the top) and copy acepro.cfg
3. Copy acepro_printer_macros.cfg (backup if exists)
4. Copy acepro_setting.cfg (backup if exists)
5. Copy acepro_macros.cfg (backup if exists)
5b. Copy cut_calibrate.cfg and spoolman_logic.cfg, enable [force_move] (needed by CUT_TIP)
6. Link KlipperScreen panel (if available)
7. Optionally restart services and check that Klipper comes up
8. Show how to install the OrcaSlicer plugin
EOF
    
    if ! prompt_yes_no "Continue with installation?"; then
        print_info "Installation cancelled"
        exit 0
    fi
    
    # ========================================================================
    # Step 1: Link ace module to Klipper extras
    # ========================================================================
    
    print_header "Step 1: Linking ACE module to Klipper extras"
    
    ACE_SOURCE="$SCRIPT_DIR/extras/ace"
    ACE_TARGET="$KLIPPER_DIR/klippy/extras/ace"
    
    if [ ! -d "$ACE_SOURCE" ]; then
        print_error "ACE source directory not found: $ACE_SOURCE"
        exit 1
    fi
    
    create_or_replace_symlink "$ACE_SOURCE" "$ACE_TARGET" "ACE module"

    VP_SOURCE="$SCRIPT_DIR/extras/virtual_pins.py"
    VP_TARGET="$KLIPPER_DIR/klippy/extras/virtual_pins.py"
    
    if [ ! -f "$VP_SOURCE" ]; then
        print_error "virtual_pins.py not found: $ACE_SOURCE"
        exit 1
    fi
    
    create_or_replace_symlink "$VP_SOURCE" "$VP_TARGET" "virtual_pins module"

    # Optional ACE temperature sensor (safe to link even if unused)
    TEMP_SOURCE="$SCRIPT_DIR/extras/temperature_ace.py"
    TEMP_TARGET="$KLIPPER_DIR/klippy/extras/temperature_ace.py"

    if [ -f "$TEMP_SOURCE" ]; then
        print_info "Linking optional ACE temperature sensor (temperature_ace.py)..."
        create_or_replace_symlink "$TEMP_SOURCE" "$TEMP_TARGET" "temperature_ace sensor"
    else
        print_warning "temperature_ace.py not found; skipping sensor symlink"
    fi

    # ========================================================================
    # Step 1b: ACE Status Integration (Optional) - Using acepro-mmu-dashboard
    # ========================================================================

    ACE_STATUS_DIR="$SCRIPT_DIR/acepro-mmu-dashboard"
    if [ -d "$ACE_STATUS_DIR" ]; then
        print_header "Step 1b: ACE Status Integration (Optional)"

        if prompt_yes_no "Install ACE status Moonraker component + dashboard symlinks?"; then
            ACE_MOONRAKER_DEFAULT="$INSTALL_HOME/moonraker"
            ACE_MAINSAIL_DEFAULT="$INSTALL_HOME/mainsail"
            ACE_FLUIDD_DEFAULT="$INSTALL_HOME/fluidd"
            ACE_MOONRAKER_CONF_DEFAULT="$INSTALL_HOME/printer_data/config/moonraker.conf"

            # Moonraker component
            ACE_MOONRAKER_DIR=$(prompt_input "Moonraker directory (press ENTER to use default)" "$ACE_MOONRAKER_DEFAULT")
            ACE_MOONRAKER_COMPONENTS="$ACE_MOONRAKER_DIR/moonraker/components"
            if [ -d "$ACE_MOONRAKER_COMPONENTS" ]; then
                ACE_STATUS_SOURCE="$ACE_STATUS_DIR/moonraker/ace_status.py"
                ACE_STATUS_TARGET="$ACE_MOONRAKER_COMPONENTS/ace_status.py"
                create_or_replace_symlink "$ACE_STATUS_SOURCE" "$ACE_STATUS_TARGET" "ACE status Moonraker component"
                MOONRAKER_RESTART_NEEDED=1

                # Ensure moonraker.conf has [ace_status]
                ACE_MOONRAKER_CONF=$(prompt_input "moonraker.conf path (press ENTER to use default)" "$ACE_MOONRAKER_CONF_DEFAULT")
                ensure_moonraker_ace_status "$ACE_MOONRAKER_CONF"
            else
                print_warning "Moonraker components directory not found: $ACE_MOONRAKER_COMPONENTS"
                print_info "Skipping Moonraker ACE status symlink"
            fi

            # Mainsail dashboard files
            if prompt_yes_no "Link dashboard files into Mainsail?"; then
                ACE_MAINSAIL_DIR=$(prompt_input "Mainsail install directory" "$ACE_MAINSAIL_DEFAULT")
                if [ -d "$ACE_MAINSAIL_DIR" ]; then
                    for ace_file in ace.html ace-dashboard.js ace-dashboard.css ace-dashboard-config.js favicon.svg; do
                        create_or_replace_symlink "$ACE_STATUS_DIR/web/$ace_file" "$ACE_MAINSAIL_DIR/$ace_file" "Mainsail $ace_file"
                    done
                else
                    print_warning "Mainsail directory not found: $ACE_MAINSAIL_DIR"
                    print_info "Skipped Mainsail dashboard links"
                fi
            fi

            # Fluidd dashboard files
            if prompt_yes_no "Link dashboard files into Fluidd?"; then
                ACE_FLUIDD_DIR=$(prompt_input "Fluidd install directory" "$ACE_FLUIDD_DEFAULT")
                if [ -d "$ACE_FLUIDD_DIR" ]; then
                    for ace_file in ace.html ace-dashboard.js ace-dashboard.css ace-dashboard-config.js favicon.svg; do
                        create_or_replace_symlink "$ACE_STATUS_DIR/web/$ace_file" "$ACE_FLUIDD_DIR/$ace_file" "Fluidd $ace_file"
                    done
                else
                    print_warning "Fluidd directory not found: $ACE_FLUIDD_DIR"
                    print_info "Skipped Fluidd dashboard links"
                fi
            fi

            # ===== Ensure dashboard source files are world-readable =====
            print_info "Setting permissions 644 on ACE dashboard source files..."
            if chmod 644 "$ACE_STATUS_DIR"/web/* 2>/dev/null; then
                print_success "Permissions set on dashboard files"
            else
                print_warning "Could not set permissions (maybe files already OK?)"
            fi

        else
            print_info "ACE status integration skipped"
        fi
    else
        print_warning "Dashboard directory not found: $ACE_STATUS_DIR"
        print_info "Skipping ACE status integration (directory missing)"
    fi
    
    # ========================================================================
    # Step 1c: Python packages for the driver
    # ========================================================================

    print_header "Step 1c: Python packages"

    KLIPPY_PY="$INSTALL_HOME/klippy-env/bin/python"
    [ -x "$KLIPPY_PY" ] || KLIPPY_PY="$(command -v python3)"
    if "$KLIPPY_PY" -c "import serial, jinja2" 2>/dev/null; then
        print_success "pyserial and jinja2 are available in $KLIPPY_PY"
    else
        print_warning "pyserial or jinja2 is missing in $KLIPPY_PY"
        if prompt_yes_no "Install them now (pip install pyserial jinja2)?"; then
            "$KLIPPY_PY" -m pip install "pyserial>=3.4" "jinja2>=3.0.0" \
                && print_success "Packages installed" \
                || print_error "pip failed. Run it yourself: $KLIPPY_PY -m pip install pyserial jinja2"
        fi
    fi
    if "$KLIPPY_PY" -m compileall -q "$SCRIPT_DIR/extras" >/dev/null 2>&1; then
        print_success "Driver files compile (syntax OK)"
    else
        print_warning "The driver did not compile with $KLIPPY_PY. Check its Python version (3.9 or newer)."
    fi

    # ========================================================================
    # Step 1d: Fluidd ACE Pro card + spool picker (Optional)
    # ========================================================================

    print_header "Step 1d: Fluidd ACE panel (Optional)"

    echo "Adds an ACE Pro card to the Fluidd dashboard and the 'Choose ACE spools' window"
    echo "that opens when you press Print. Needs Moonraker's ace_status (step 1b)."
    FLUIDD_PANEL_INSTALLED=0
    if prompt_yes_no "Install the Fluidd ACE panel (Fluidd 1.37.7 build from this repository)?"; then
        FLUIDD_DIR=$(prompt_input "Fluidd install directory" "$INSTALL_HOME/fluidd")
        if install_fluidd_panel "$FLUIDD_DIR"; then
            FLUIDD_PANEL_INSTALLED=1
        fi
    else
        print_info "Fluidd panel skipped"
    fi

    # ========================================================================
    # Step 2: Ensure printer.cfg includes acepro.cfg (at the top) and copy acepro.cfg
    # ========================================================================
    
    print_header "Step 2: Printer Configuration Integration"
    
    # Copy acepro.cfg (the main ACE config) to config directory
    ACEPRO_SOURCE="$SCRIPT_DIR/config/acepro.cfg"
    ACEPRO_TARGET="$CONFIG_DIR/acepro.cfg"
    
    if [ ! -f "$ACEPRO_SOURCE" ]; then
        print_error "acepro.cfg not found: $ACEPRO_SOURCE"
        exit 1
    fi
    
    # Handle acepro.cfg copy (with backup)
    if [ -f "$ACEPRO_TARGET" ]; then
        print_warning "acepro.cfg already exists in config directory"
        local was_symlink=0
        if is_symlink "$ACEPRO_TARGET"; then
            was_symlink=1
            print_info "Current acepro.cfg is a symlink (→ $(readlink "$ACEPRO_TARGET"))"
        fi

        if ! prompt_yes_no "Back up and replace acepro.cfg?"; then
            print_info "Skipped acepro.cfg installation"
        else
            local timestamp=$(date +"%Y%m%d_%H%M%S")
            local backup="${ACEPRO_TARGET}.backup_${timestamp}"
            cp "$ACEPRO_TARGET" "$backup"
            print_success "Backed up: $ACEPRO_TARGET → $backup"

            if [ "$was_symlink" -eq 1 ]; then
                remove_symlink_if_exists "$ACEPRO_TARGET"
            fi

            cp "$ACEPRO_SOURCE" "$ACEPRO_TARGET"
            print_success "Copied: $ACEPRO_SOURCE → $ACEPRO_TARGET"
        fi
    else
        cp "$ACEPRO_SOURCE" "$ACEPRO_TARGET"
        print_success "Copied: $ACEPRO_SOURCE → $ACEPRO_TARGET"
    fi
    
    # Now ensure printer.cfg includes acepro.cfg (at the top)
    PRINTER_CFG="$CONFIG_DIR/printer.cfg"
    ensure_include_in_printer_cfg "$PRINTER_CFG"
    
    # ========================================================================
    # Step 3: Copy acepro_printer_macros.cfg
    # ========================================================================

    print_header "Step 3: Printer Generic Macros"

    PRINTER_GENERIC_MACROS_SOURCE="$SCRIPT_DIR/config/acepro_printer_macros.cfg"
    PRINTER_GENERIC_MACROS_TARGET="$CONFIG_DIR/acepro_printer_macros.cfg"

    if [ ! -f "$PRINTER_GENERIC_MACROS_SOURCE" ]; then
        print_error "acepro_printer_macros.cfg not found: $PRINTER_GENERIC_MACROS_SOURCE"
        exit 1
    fi

    if [ -f "$PRINTER_GENERIC_MACROS_TARGET" ]; then
        print_warning "acepro_printer_macros.cfg already exists"
        local was_symlink=0
        if is_symlink "$PRINTER_GENERIC_MACROS_TARGET"; then
            was_symlink=1
            print_info "Current acepro_printer_macros.cfg is a symlink (→ $(readlink "$PRINTER_GENERIC_MACROS_TARGET"))"
        fi

        if ! prompt_yes_no "Back up and replace acepro_printer_macros.cfg?"; then
            print_info "Skipped acepro_printer_macros.cfg installation"
        else
            local timestamp=$(date +"%Y%m%d_%H%M%S")
            PRINTER_GENERIC_MACROS_BACKUP="${PRINTER_GENERIC_MACROS_TARGET}.backup_${timestamp}"
            cp "$PRINTER_GENERIC_MACROS_TARGET" "$PRINTER_GENERIC_MACROS_BACKUP"
            print_success "Backed up: $PRINTER_GENERIC_MACROS_TARGET → $PRINTER_GENERIC_MACROS_BACKUP"

            if [ "$was_symlink" -eq 1 ]; then
                remove_symlink_if_exists "$PRINTER_GENERIC_MACROS_TARGET"
            fi

            cp "$PRINTER_GENERIC_MACROS_SOURCE" "$PRINTER_GENERIC_MACROS_TARGET"
            print_success "Copied: $PRINTER_GENERIC_MACROS_SOURCE → $PRINTER_GENERIC_MACROS_TARGET"
        fi
    else
        cp "$PRINTER_GENERIC_MACROS_SOURCE" "$PRINTER_GENERIC_MACROS_TARGET"
        print_success "Copied: $PRINTER_GENERIC_MACROS_SOURCE → $PRINTER_GENERIC_MACROS_TARGET"
    fi

    # Legacy filename support (cleanup old printer_macros_generic.cfg symlinks)
    LEGACY_PRINTER_GENERIC_MACROS_TARGET="$CONFIG_DIR/printer_macros_generic.cfg"
    if is_symlink "$LEGACY_PRINTER_GENERIC_MACROS_TARGET"; then
        print_warning "Legacy printer_macros_generic.cfg symlink detected"
        print_info "Current printer_macros_generic.cfg is a symlink (→ $(readlink "$LEGACY_PRINTER_GENERIC_MACROS_TARGET"))"

        if prompt_yes_no "Replace printer_macros_generic.cfg with a local copy?"; then
            local timestamp=$(date +"%Y%m%d_%H%M%S")
            local legacy_backup="${LEGACY_PRINTER_GENERIC_MACROS_TARGET}.backup_${timestamp}"
            cp "$LEGACY_PRINTER_GENERIC_MACROS_TARGET" "$legacy_backup"
            print_success "Backed up: $LEGACY_PRINTER_GENERIC_MACROS_TARGET → $legacy_backup"

            remove_symlink_if_exists "$LEGACY_PRINTER_GENERIC_MACROS_TARGET"
            cp "$PRINTER_GENERIC_MACROS_SOURCE" "$LEGACY_PRINTER_GENERIC_MACROS_TARGET"
            print_success "Copied: $PRINTER_GENERIC_MACROS_SOURCE → $LEGACY_PRINTER_GENERIC_MACROS_TARGET"
        else
            print_info "Skipped printer_macros_generic.cfg replacement"
        fi
    fi

    # ========================================================================
    # Step 4: Copy ACE configuration file (acepro_setting.cfg)
    # ========================================================================

    print_header "Step 4: ACE Configuration Files"

    ACE_CONFIG_SOURCE="$SCRIPT_DIR/config/acepro_setting.cfg"
    ACE_CONFIG_TARGET="$CONFIG_DIR/acepro_setting.cfg"

    if [ ! -f "$ACE_CONFIG_SOURCE" ]; then
        print_error "ACE config file not found: $ACE_CONFIG_SOURCE"
        exit 1
    fi

    if [ -f "$ACE_CONFIG_TARGET" ]; then
        print_warning "acepro_setting.cfg already exists"
        local was_symlink=0
        if is_symlink "$ACE_CONFIG_TARGET"; then
            was_symlink=1
            print_info "Current acepro_setting.cfg is a symlink (→ $(readlink "$ACE_CONFIG_TARGET"))"
        fi

        if ! prompt_yes_no "Back up and replace acepro_setting.cfg?"; then
            print_info "Skipped acepro_setting.cfg installation"
        else
            local timestamp=$(date +"%Y%m%d_%H%M%S")
            ACE_CONFIG_BACKUP="${ACE_CONFIG_TARGET}.backup_${timestamp}"
            cp "$ACE_CONFIG_TARGET" "$ACE_CONFIG_BACKUP"
            print_success "Backed up: $ACE_CONFIG_TARGET → $ACE_CONFIG_BACKUP"

            if [ "$was_symlink" -eq 1 ]; then
                remove_symlink_if_exists "$ACE_CONFIG_TARGET"
            fi

            cp "$ACE_CONFIG_SOURCE" "$ACE_CONFIG_TARGET"
            print_success "Copied: $ACE_CONFIG_SOURCE → $ACE_CONFIG_TARGET"
        fi
    else
        cp "$ACE_CONFIG_SOURCE" "$ACE_CONFIG_TARGET"
        print_success "Copied: $ACE_CONFIG_SOURCE → $ACE_CONFIG_TARGET"
    fi

    # ========================================================================
    # Step 5: Copy ACE macro file (acepro_macros.cfg)
    # ========================================================================

    print_header "Step 5: ACE Macro Files"

    MACROS_SOURCE="$SCRIPT_DIR/config/acepro_macros.cfg"
    MACROS_TARGET="$CONFIG_DIR/acepro_macros.cfg"

    if [ ! -f "$MACROS_SOURCE" ]; then
        print_error "ACE macros file not found: $MACROS_SOURCE"
        exit 1
    fi

    if [ -f "$MACROS_TARGET" ]; then
        print_warning "acepro_macros.cfg already exists"
        local was_symlink=0
        if is_symlink "$MACROS_TARGET"; then
            was_symlink=1
            print_info "Current acepro_macros.cfg is a symlink (→ $(readlink "$MACROS_TARGET"))"
        fi

        if ! prompt_yes_no "Back up and replace acepro_macros.cfg?"; then
            print_info "Skipped acepro_macros.cfg installation"
        else
            local timestamp=$(date +"%Y%m%d_%H%M%S")
            ACE_MACROS_BACKUP="${MACROS_TARGET}.backup_${timestamp}"
            cp "$MACROS_TARGET" "$ACE_MACROS_BACKUP"
            print_success "Backed up: $MACROS_TARGET → $ACE_MACROS_BACKUP"

            if [ "$was_symlink" -eq 1 ]; then
                remove_symlink_if_exists "$MACROS_TARGET"
            fi

            cp "$MACROS_SOURCE" "$MACROS_TARGET"
            print_success "Copied: $MACROS_SOURCE → $MACROS_TARGET"
        fi
    else
        cp "$MACROS_SOURCE" "$MACROS_TARGET"
        print_success "Copied: $MACROS_SOURCE → $MACROS_TARGET"
    fi
    
    # ========================================================================
    # Step 5b: Cutter calibration, Spoolman helpers, force_move
    # ========================================================================

    print_header "Step 5b: Extra config files"

    install_optional_cfg "$SCRIPT_DIR/config/cut_calibrate.cfg" "$CONFIG_DIR/cut_calibrate.cfg" "cut_calibrate.cfg"
    install_optional_cfg "$SCRIPT_DIR/config/spoolman_logic.cfg" "$CONFIG_DIR/spoolman_logic.cfg" "spoolman_logic.cfg"

    echo ""
    print_info "CUT_TIP needs [force_move] enabled."
    if prompt_yes_no "Make sure [force_move] enable_force_move: True is in printer.cfg?"; then
        ensure_force_move "$PRINTER_CFG"
    fi
    echo ""
    print_info "cut_calibrate.cfg adds CUT_CAL_START / CUT_CAL_STEP / CUT_CAL_END to find where the cutter closes."
    if prompt_yes_no "Add [include cut_calibrate.cfg] to printer.cfg now?"; then
        ensure_include_line "$PRINTER_CFG" "[include cut_calibrate.cfg]"
    else
        print_info "Skipped. Add [include cut_calibrate.cfg] when you want to calibrate (README section 9)."
    fi

    # ========================================================================
    # Step 6: Link KlipperScreen panel (if available)
    # ========================================================================

    print_header "Step 6: KlipperScreen Integration (Optional)"
    
    KLIPPERSCREEN_ROOT_DIR="$INSTALL_HOME/KlipperScreen"
    KLIPPERSCREEN_PANELS_DIR="$KLIPPERSCREEN_ROOT_DIR/panels"
    KLIPPERSCREEN_PANEL_SOURCE="$SCRIPT_DIR/KlipperScreen/acepro.py"
    KLIPPERSCREEN_PANEL_TARGET="$KLIPPERSCREEN_PANELS_DIR/acepro.py"
    
    if [ ! -d "$KLIPPERSCREEN_PANELS_DIR" ]; then
        print_warning "KlipperScreen panels directory not found: $KLIPPERSCREEN_PANELS_DIR"
        print_info "KlipperScreen integration skipped (not installed)"
    else
        if [ ! -f "$KLIPPERSCREEN_PANEL_SOURCE" ]; then
            print_error "KlipperScreen panel file not found: $KLIPPERSCREEN_PANEL_SOURCE"
        else
            print_info "KlipperScreen panels directory found"
            create_or_replace_symlink "$KLIPPERSCREEN_PANEL_SOURCE" "$KLIPPERSCREEN_PANEL_TARGET" "acepro.py panel"
        fi
    fi

    # Optional: patch KlipperScreen core to subscribe to ACE objects
    KLIPPERSCREEN_PATCH="$SCRIPT_DIR/patches/ace_global_subscription.patch"
    if [ -d "$KLIPPERSCREEN_ROOT_DIR" ] && [ -f "$KLIPPERSCREEN_PATCH" ]; then
        echo ""
        print_info "ACE patch available for KlipperScreen core subscription."
        if prompt_yes_no "Apply ACE KlipperScreen patch now?"; then
            print_info "Checking ACE patch applicability..."
            if patch -d "$KLIPPERSCREEN_ROOT_DIR" -p1 --forward --dry-run < "$KLIPPERSCREEN_PATCH"; then
                print_info "Applying ACE patch to $KLIPPERSCREEN_ROOT_DIR"
                if patch -d "$KLIPPERSCREEN_ROOT_DIR" -p1 --forward < "$KLIPPERSCREEN_PATCH"; then
                    print_success "KlipperScreen patch applied"
                else
                    print_warning "Patch failed during apply (unexpected). Please review output."
                fi
            else
                print_warning "Patch did not apply cleanly (likely already applied or conflicting changes). Skipping."
            fi
        else
            print_info "Skipped KlipperScreen patch (you can apply $KLIPPERSCREEN_PATCH manually later)"
        fi
    fi

    # Ensure KlipperScreen.conf has font_size = small and ACE Pro menu entry
    if [ -d "$KLIPPERSCREEN_ROOT_DIR" ]; then
        KLIPPERSCREEN_CONF="$CONFIG_DIR/KlipperScreen.conf"
        echo ""
        print_info "Checking KlipperScreen.conf for font_size setting..."
        ensure_klipperscreen_font_size "$KLIPPERSCREEN_CONF"
        print_info "Checking KlipperScreen.conf for ACE Pro menu entries (main + print menus)..."
        ensure_klipperscreen_acepro_menu "$KLIPPERSCREEN_CONF"
    fi
    
    # ========================================================================
    # Step 7: Service restart
    # ========================================================================

    print_header "Step 7: Service Restart"
    
    echo "Moonraker (if ACE status was linked), Klipper and KlipperScreen need to be restarted for changes to take effect."
    echo ""

    if [ "$MOONRAKER_RESTART_NEEDED" -eq 1 ]; then
        if prompt_yes_no "Restart Moonraker service now?"; then
            print_info "Restarting Moonraker..."
            sudo systemctl restart moonraker
            if [ $? -eq 0 ]; then
                print_success "Moonraker restarted"
            else
                print_error "Failed to restart Moonraker"
            fi
        else
            print_warning "Moonraker not restarted. You can restart manually:"
            echo "  sudo systemctl restart moonraker"
        fi
        echo ""
    fi

    if prompt_yes_no "Restart Klipper service now?"; then
        print_info "Restarting Klipper..."
        sudo systemctl restart klipper
        if [ $? -eq 0 ]; then
            print_success "Klipper restarted"
        else
            print_error "Failed to restart Klipper"
        fi
    else
        print_warning "Klipper not restarted. You can restart manually:"
        echo "  sudo systemctl restart klipper"
    fi
    
    # Wait for Klipper and report whether the ACE units came up
    if command -v curl >/dev/null 2>&1 && curl -s -m 3 http://127.0.0.1:7125/server/info >/dev/null 2>&1; then
        print_info "Waiting for Klipper to start..."
        KLIPPY_STATE=""
        for _ in $(seq 1 30); do
            sleep 2
            KLIPPY_STATE=$(curl -s -m 3 http://127.0.0.1:7125/server/info | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["klippy_state"])' 2>/dev/null || echo "")
            case "$KLIPPY_STATE" in ready|error|shutdown) break ;; esac
        done
        case "$KLIPPY_STATE" in
            ready)
                print_success "Klipper is ready"
                ACE_SEEN=$(curl -s -m 3 "http://127.0.0.1:7125/printer/objects/list" | python3 -c 'import sys,json; print(sum(1 for o in json.load(sys.stdin)["result"]["objects"] if o=="ace" or o.startswith("ace_instance")))' 2>/dev/null || echo 0)
                if [ "${ACE_SEEN:-0}" -gt 0 ] 2>/dev/null; then
                    print_success "ACE driver loaded ($ACE_SEEN ACE objects). Run ACE_GET_STATUS in the console."
                else
                    print_warning "Klipper is ready but the ACE driver is not loaded. Check that printer.cfg has [include acepro.cfg]."
                fi
                ;;
            "") print_warning "Could not read Klipper's state. Check Fluidd." ;;
            *)  print_error "Klipper state: $KLIPPY_STATE. Read the error in Fluidd or ~/printer_data/logs/klippy.log" ;;
        esac
    fi

    if [ -d "$KLIPPERSCREEN_PANELS_DIR" ]; then
        echo ""
        if prompt_yes_no "Restart KlipperScreen service now?"; then
            print_info "Restarting KlipperScreen..."
            sudo systemctl restart KlipperScreen 2>/dev/null || \
            sudo supervisorctl restart klipperscreen 2>/dev/null || \
            print_warning "Could not restart KlipperScreen. You can restart manually or via supervisor"
            if [ $? -eq 0 ]; then
                print_success "KlipperScreen restarted"
            fi
        else
            print_warning "KlipperScreen not restarted. You can restart manually:"
            echo "  sudo systemctl restart KlipperScreen"
            echo "  or: sudo supervisorctl restart klipperscreen"
        fi
    fi
    
    # ========================================================================
    # Installation complete
    # ========================================================================
    
    print_header "Installation Complete!"
    
    cat << EOF
ACE Pro driver installation finished!
EOF
    if [ "${FLUIDD_PANEL_INSTALLED:-0}" -eq 1 ]; then
        echo "  Fluidd ACE panel:               installed (backup of the old Fluidd: ${FLUIDD_DIR}_backup_*)"
    fi
    cat << EOF

Configuration Files:
  Main ACE config:               $ACEPRO_TARGET
  ACE settings:                   $ACE_CONFIG_TARGET
  ACE macros:                     $MACROS_TARGET
  Printer generic macros:         $PRINTER_GENERIC_MACROS_TARGET
EOF
    
    # Show backup files if any were created
    if [ -n "$ACE_CONFIG_BACKUP" ] && [ -f "$ACE_CONFIG_BACKUP" ]; then
        echo "  Backed up acepro_setting.cfg: $ACE_CONFIG_BACKUP"
    fi
    if [ -n "$ACE_MACROS_BACKUP" ] && [ -f "$ACE_MACROS_BACKUP" ]; then
        echo "  Backed up acepro_macros.cfg: $ACE_MACROS_BACKUP"
    fi
    if [ -n "$PRINTER_GENERIC_MACROS_BACKUP" ] && [ -f "$PRINTER_GENERIC_MACROS_BACKUP" ]; then
        echo "  Backed up acepro_printer_macros.cfg: $PRINTER_GENERIC_MACROS_BACKUP"
    fi
    
    cat << EOF

Next steps:
  1. Review and customize ACE configuration:
      $ACE_CONFIG_TARGET
      - Set ace_count to number of ACE units
      - Adjust feed/retract speeds
      - Configure sensor pins if needed
      - Re-run installer after updates to pick up template changes

  2. Your printer.cfg now includes acepro.cfg at the top (if you chose to add it).
     If not, manually add:
        [include acepro.cfg]
     to your $PRINTER_CFG

  3. Review acepro_printer_macros.cfg if you plan to customize pause/resume, velocity stack, or purge helpers:
      $PRINTER_GENERIC_MACROS_TARGET

  4. Review acepro_macros.cfg if you plan to tweak ACE hooks or safety wrappers:
      $MACROS_TARGET

  5. Restart Klipper if not already restarted:
     sudo systemctl restart klipper

  6. Test basic commands in Klipper console:
     e.g. ACE_GET_STATUS

  7. Optional but recommended: Set inventory for each tool:
     ACE_SET_SLOT INSTANCE=0 INDEX=0 COLOR=255,0,0 MATERIAL=PLA TEMP=210

  8. OrcaSlicer 2.5 (runs on your computer, not on the printer):
     a) Copy the plugin to your computer, for example:
          scp $INSTALL_USER@<printer-ip>:$SCRIPT_DIR/orca_plugin/ace_spool_mapper.py .
     b) Orca: File -> Plugins -> Browse plugins -> Install local plugin -> pick the file.
     c) Follow $SCRIPT_DIR/orca_plugin/INSTALL.md (Process -> Others -> Slicing Pipeline Plugin).
     d) Optional: slicer/orca_flush_to_purgelength.py converts flush volumes to purge lengths.
     Slicer start G-code and the other steps: README.md, section 5.

  9. Fluidd and KlipperScreen: hard-refresh the browser (Ctrl/Cmd+Shift+R). Press Print on a file
     to see the "Choose ACE spools" window.

 10. Calibrate the cutter before the first multi-colour print (README.md, section 9):
     CUT_CAL_START, CUT_CAL_STEP (repeat), CUT_CAL_END, then set cut_full_x in acepro_macros.cfg.

EOF
}

# ============================================================================
# Entry Point
# ============================================================================

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi