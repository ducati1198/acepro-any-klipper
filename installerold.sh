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
2. Ensure printer.cfg includes acepro.cfg (at the top) and copy acepro.cfg
3. Copy acepro_printer_macros.cfg (backup if exists)
4. Copy acepro_setting.cfg (backup if exists)
5. Copy acepro_macros.cfg (backup if exists)
6. Link optional ACE temperature sensor
7. Link KlipperScreen panel (if available)
8. Optionally restart services
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
    # Step 1b: ACE Status Integration (Optional)
    # ========================================================================

    ACE_STATUS_DIR="$SCRIPT_DIR/ace_status_integration"
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

            # ===== NEW: Ensure dashboard source files are world-readable =====
            print_info "Setting permissions 644 on ACE dashboard source files..."
            if chmod 644 "$ACE_STATUS_DIR"/web/* 2>/dev/null; then
                print_success "Permissions set on dashboard files"
            else
                print_warning "Could not set permissions (maybe files already OK?)"
            fi

        else
            print_info "ACE status integration skipped"
        fi
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
    elif [ ! -f "$KLIPPERSCREEN_PATCH" ]; then
        print_warning "KlipperScreen patch file not found: $KLIPPERSCREEN_PATCH"
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

  8. If using Orca Slicer:
     Install the orca_flush_to_purgelength.py post-processing script on your host PC
     See README.md section on Orca Slicer integration for detailed instructions

EOF
}

# ============================================================================
# Entry Point
# ============================================================================

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi