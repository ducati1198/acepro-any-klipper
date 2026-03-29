#!/bin/bash

# =============================================================================
# ACE Dashboard - Interactive Installer
# =============================================================================
# This script installs the ACE Dashboard web files into Mainsail/Fluidd
# and installs the Moonraker component for ACE status.
#
# Usage: ./install.sh
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

# Resolve installation user/home for defaults
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

# Create or replace symlink
create_or_replace_symlink() {
    local source="$1"
    local target="$2"
    local description="$3"
    
    if [ ! -e "$source" ]; then
        print_error "$source does not exist, skipping symlink"
        return 1
    fi
    
    if [ -e "$target" ] || is_symlink "$target" ]; then
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

# ============================================================================
# Main Installation
# ============================================================================

main() {
    print_header "ACE Dashboard - Interactive Installer"
    
    local moonraker_changed=0
    local restart_moonraker=0

    # ========================================================================
    # Step 1: Determine source directory
    # ========================================================================
    
    print_info "Locating ACE Dashboard source files..."
    
    # Default: assume the script is in the root of the repo and source files are in acepro_dashboard/
    DEFAULT_SOURCE_DIR="$SCRIPT_DIR/acepro_dashboard"
    
    # Check if the default exists; if not, try SCRIPT_DIR itself
    if [ -d "$DEFAULT_SOURCE_DIR/web" ] && [ -d "$DEFAULT_SOURCE_DIR/moonraker" ]; then
        SOURCE_DIR="$DEFAULT_SOURCE_DIR"
        print_success "Found source files in $SOURCE_DIR"
    elif [ -d "$SCRIPT_DIR/web" ] && [ -d "$SCRIPT_DIR/moonraker" ]; then
        SOURCE_DIR="$SCRIPT_DIR"
        print_success "Found source files in $SOURCE_DIR"
    else
        print_warning "Could not automatically locate the 'web' and 'moonraker' folders."
        SOURCE_DIR=$(prompt_input "Please enter the full path to the directory containing 'web' and 'moonraker' subfolders" "$DEFAULT_SOURCE_DIR")
    fi

    # Validate that web/ and moonraker/ exist under SOURCE_DIR
    if [ ! -d "$SOURCE_DIR/web" ]; then
        print_error "web directory not found at $SOURCE_DIR/web"
        exit 1
    fi
    if [ ! -d "$SOURCE_DIR/moonraker" ]; then
        print_error "moonraker directory not found at $SOURCE_DIR/moonraker"
        exit 1
    fi

    # ========================================================================
    # Step 2: Gather user input for target locations
    # ========================================================================
    
    print_info "Installation source confirmed: $SOURCE_DIR"
    print_info "Source web files: $SOURCE_DIR/web/"
    print_info "Source moonraker component: $SOURCE_DIR/moonraker/ace_status.py"

    # 2.1 Ask about Mainsail
    if prompt_yes_no "\nInstall dashboard files into Mainsail?"; then
        DEFAULT_MAINSAIL_DIR="$INSTALL_HOME/mainsail"
        MAINSAIL_DIR=$(prompt_input "Mainsail installation directory" "$DEFAULT_MAINSAIL_DIR")
        if [ ! -d "$MAINSAIL_DIR" ]; then
            print_warning "Mainsail directory not found: $MAINSAIL_DIR"
            if ! prompt_yes_no "Directory does not exist. Create symlinks anyway?"; then
                MAINSAIL_DIR=""
            fi
        fi
    else
        MAINSAIL_DIR=""
    fi

    # 2.2 Ask about Fluidd
    if prompt_yes_no "\nInstall dashboard files into Fluidd?"; then
        DEFAULT_FLUIDD_DIR="$INSTALL_HOME/fluidd"
        FLUIDD_DIR=$(prompt_input "Fluidd installation directory" "$DEFAULT_FLUIDD_DIR")
        if [ ! -d "$FLUIDD_DIR" ]; then
            print_warning "Fluidd directory not found: $FLUIDD_DIR"
            if ! prompt_yes_no "Directory does not exist. Create symlinks anyway?"; then
                FLUIDD_DIR=""
            fi
        fi
    else
        FLUIDD_DIR=""
    fi

    # 2.3 Ask about Moonraker component
    if prompt_yes_no "\nInstall Moonraker ACE status component?"; then
        DEFAULT_MOONRAKER_DIR="$INSTALL_HOME/moonraker"
        MOONRAKER_DIR=$(prompt_input "Moonraker installation directory" "$DEFAULT_MOONRAKER_DIR")
        if [ ! -d "$MOONRAKER_DIR" ]; then
            print_error "Moonraker directory not found: $MOONRAKER_DIR"
            print_info "Skipping Moonraker component installation."
            MOONRAKER_DIR=""
        else
            DEFAULT_MOONRAKER_CONF="$INSTALL_HOME/printer_data/config/moonraker.conf"
            MOONRAKER_CONF=$(prompt_input "moonraker.conf path" "$DEFAULT_MOONRAKER_CONF")
        fi
    else
        MOONRAKER_DIR=""
    fi

    # ========================================================================
    # Step 3: Show summary and ask for confirmation
    # ========================================================================
    
    echo ""
    print_header "Installation Summary"
    
    if [ -n "$MAINSAIL_DIR" ]; then
        echo "Mainsail: $MAINSAIL_DIR"
    else
        echo "Mainsail: not selected"
    fi
    if [ -n "$FLUIDD_DIR" ]; then
        echo "Fluidd:   $FLUIDD_DIR"
    else
        echo "Fluidd:   not selected"
    fi
    if [ -n "$MOONRAKER_DIR" ]; then
        echo "Moonraker component: $MOONRAKER_DIR/moonraker/components/"
        echo "Moonraker config:    $MOONRAKER_CONF"
    else
        echo "Moonraker component: not selected"
    fi
    
    if ! prompt_yes_no "\nProceed with installation?"; then
        print_info "Installation cancelled"
        exit 0
    fi
    
    # ========================================================================
    # Step 4: Link web files to Mainsail/Fluidd
    # ========================================================================
    
    if [ -n "$MAINSAIL_DIR" ]; then
        print_header "Linking dashboard files into Mainsail"
        for file in ace.html ace-dashboard.js ace-dashboard.css ace-dashboard-config.js favicon.svg; do
            create_or_replace_symlink "$SOURCE_DIR/web/$file" "$MAINSAIL_DIR/$file" "Mainsail $file"
        done
    fi
    
    if [ -n "$FLUIDD_DIR" ]; then
        print_header "Linking dashboard files into Fluidd"
        for file in ace.html ace-dashboard.js ace-dashboard.css ace-dashboard-config.js favicon.svg; do
            create_or_replace_symlink "$SOURCE_DIR/web/$file" "$FLUIDD_DIR/$file" "Fluidd $file"
        done
    fi
    
    # ========================================================================
    # Step 5: Install Moonraker component and update config
    # ========================================================================
    
    if [ -n "$MOONRAKER_DIR" ]; then
        print_header "Installing Moonraker ACE status component"
        ACE_STATUS_SOURCE="$SOURCE_DIR/moonraker/ace_status.py"
        ACE_STATUS_TARGET="$MOONRAKER_DIR/moonraker/components/ace_status.py"
        if [ -f "$ACE_STATUS_SOURCE" ]; then
            create_or_replace_symlink "$ACE_STATUS_SOURCE" "$ACE_STATUS_TARGET" "Moonraker ace_status component"
            if [ $? -eq 0 ]; then
                moonraker_changed=1
            fi
        else
            print_error "ace_status.py not found at $ACE_STATUS_SOURCE"
        fi

        # Ensure moonraker.conf has [ace_status]
        if [ -n "$MOONRAKER_CONF" ]; then
            ensure_moonraker_ace_status "$MOONRAKER_CONF"
            moonraker_changed=1
        fi
    fi
    
    # ========================================================================
    # Step 6: Set permissions on source web files (ensure they are readable)
    # ========================================================================
    
    print_header "Setting file permissions"
    print_info "Making source web files world-readable (644)..."
    if chmod 644 "$SOURCE_DIR"/web/* 2>/dev/null; then
        print_success "Permissions set on web files"
    else
        print_warning "Could not set permissions (maybe files already OK?)"
    fi
    
    # ========================================================================
    # Step 7: Restart Moonraker if needed
    # ========================================================================
    
    if [ $moonraker_changed -eq 1 ]; then
        print_header "Moonraker Restart"
        echo "The Moonraker component and/or configuration have been updated."
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
    fi
    
    # ========================================================================
    # Step 8: Installation complete
    # ========================================================================
    
    print_header "Installation Complete!"
    
    cat << EOF
The ACE Dashboard has been installed.

- Web files linked to: ${MAINSAIL_DIR:-none} ${FLUIDD_DIR:-none}
- Moonraker component: ${MOONRAKER_DIR:-not installed}
- Moonraker config updated: ${MOONRAKER_CONF:-no changes}

Next steps:
  1. Open your dashboard at:
     http://<your-printer-ip>/ace.html

  2. If needed, adjust the API host in ace-dashboard-config.js
     (edit the file at its source location: $SOURCE_DIR/web/ace-dashboard-config.js)

  3. (Optional) Review the provided nginx configuration snippet:
     $SOURCE_DIR/web/ace_dashboard.nginx.conf
     This can be used if you need to proxy Moonraker on the same host.

  4. Enjoy controlling your ACE units from the browser!
EOF
}

# ============================================================================
# Entry Point
# ============================================================================

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
