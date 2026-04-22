Below is the complete content of the `README.md` file. You can copy it directly into a new file on your computer and save it as `README.md`.

```markdown
# ACE Pro – Klipper Driver for Anycubic ACE Pro (Any Printer)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Klipper](https://img.shields.io/badge/Klipper-required-green.svg)](https://www.klipper3d.org/)

A powerful, easy‑to‑install Klipper extension that brings the **Anycubic ACE Pro** multi‑material unit to **any** Klipper‑based printer – not just Anycubic models.  
Automatically handles filament loading, tool changes, purging, wiping, and even a servo‑controlled poop basket, with smart sensor feedback and endless spool support.

**Now supports up to 3 ACE Pro units (12 tools), and more are possible.**

---

## 📋 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Integration with Your Macros](#-integration-with-your-macros)
- [Slicer Setup (OrcaSlicer)](#-slicer-setup-orcaslicer)
- [Usage & Commands](#-usage--commands)
- [Endless Spool](#-endless-spool)
- [Connection Supervision](#-connection-supervision)
- [KlipperScreen Panel (Optional)](#-klipperscreen-panel-optional)
- [Troubleshooting](#-troubleshooting)
- [Credits & License](#-credits--license)

---

## ✨ Features

### Core Functionality

- ✅ **Any Klipper Printer** – Works with Voron, RatRig, Kobra, or any other Klipper machine.
- ✅ **Multi‑ACE Support** – Tested with up to 3 units (12 tools); more should be possible.
- ✅ **Smart Tool Changes** – Automatic retraction, cutting, purging, and wiping.
- ✅ **Servo‑Controlled Poop Basket** – Deploys/retracts during tool changes, pauses, and heating.
- ✅ **Endless Spool** – Auto‑switches to a matching spool on runout (exact match, material only, or next ready).
- ✅ **Sensor‑Assisted Unload** – Uses optional RDM (splitter) and toolhead sensors for precise retraction.
- ✅ **Customisable Wipe Patterns** – Straight or zigzag, adjustable speed, length, and repetition.
- ✅ **Runout Detection** – Fully integrated with Klipper’s filament switch sensors.
- ✅ **Connection Supervision** – Monitors ACE stability; can pause the print if connection becomes unreliable.
- ✅ **Moonraker lane_data Sync** – Keeps OrcaSlicer lane data up‑to‑date (auto‑populates filament type/color).
- ✅ **RFID Inventory Sync** – Automatically reads material/color/temperature from RFID tags (optional).
- ✅ **Persistent State** – Inventory and settings survive restarts.
- ✅ **Simple Integration Hooks** – Call `_ACE_PRO_START`, `_ACE_PRO_END`, `_ACE_PRO_CANCEL` from your own macros.
- ✅ **Simple AF Compatible** – Ready‑to‑use hooks for Simple AF’s start/end/cancel macros.

---

## 📦 Installation

### Prerequisites

- A Klipper‑based printer (any model) with Python 3.9+ and pip.
- One or more ACE Pro units, connected via USB.
- A working Klipper installation (virtualenv recommended).

``` 
### One‑Click Installer (Recommended)

```bash
cd ~
git clone -b dev https://github.com/ducati1198/acepro-any-klipper
cd acepro-any-klipper
chmod +x installer.sh
./installer.sh
```

The installer will:
- Detect your Klipper directory.
- Create symlinks for the ACE Pro Python modules.
- Optionally add the required `[include]` lines to your `printer.cfg`.
- Optionally install the **ACE Pro Dashboard** for KlipperScreen.
- Ask for your printer type

**After the installer finishes, restart Klipper**:

```bash
sudo service klipper restart
```
Then add the following to your `printer.cfg`:

```ini
[include acepro.cfg]
```

Make sure a `[save_variables]` section exists (it is used to persist inventory and tool state).

---

## ⚙️ Configuration

After installation, adjust the variables in the provided files to match your printer’s geometry and hardware.

| File | Purpose |
|------|---------|
| `acepro_macros.cfg` | Movement coordinates, wipe settings, servo angles, etc. |
| `acepro_setting.cfg` | ACE hardware parameters (feed speed, retract speed, tube lengths). |

All settings are commented. Key items to change:

- **Poop position**: `variable_poop_x`, `variable_poop_y` in `_ACE_VARS`
- **Cutter block**: `cut_block_x/y`, `cut_engage_x/y`, `cut_full_x/y`
- **Wipe start**: `wipe_start_x`, `wipe_start_y`
- **Servo pins and angles** (if different)

### Multi‑ACE Units

Set `ace_count` in `acepro_setting.cfg`:

```ini
[ace]
ace_count: 2      # Two ACE units: T0‑T3 and T4‑T7
```

Tools are mapped automatically:
- Instance 0 → T0‑T3
- Instance 1 → T4‑T7
- Instance 2 → T8‑T11

Add the following lines to your `printer.cfg` to enable the `FORCE_MOVE` safety features (optional, but recommended):

```ini
[force_move]
enable_force_move: True
```

You can place this section anywhere in the file – for example, after the `[printer]` section or near other system‑level configuration blocks. After saving, restart Klipper (`sudo service klipper restart`). This will allow the ACE Pro macros (like `CUT_TIP`) to use the built‑in `FORCE_MOVE` command safely.

### Sensor Configuration

Both `filament_switch_sensor` and `filament_tracker` are supported. Example:

```ini
[filament_switch_sensor filament_runout_nozzle]
switch_pin: !nozzle_mcu:PA10
pause_on_runout: True

[filament_switch_sensor filament_runout_rdm]   # optional
switch_pin: PF1
pause_on_runout: False
```

Set the sensor names in `acepro_setting.cfg`:

```ini
filament_runout_sensor_name_nozzle: filament_runout_nozzle
filament_runout_sensor_name_rdm: filament_runout_rdm
```

### Per‑Instance Overrides

Some parameters can be set per ACE unit using a comma‑syntax. Example:

```ini
feed_speed: 60,1:45          # Instance 0: 60, Instance 1: 45
retract_speed: 50,1:40
toolchange_load_length: 2000,1:2500
```

---

## 🔌 Integration with Your Macros

We provide three simple hook macros that you can call from your own `PRINT_START`, `PRINT_END`, and `CANCEL_PRINT` macros. They are hidden from the UI (starting with `_`) but fully functional.

| Macro | Purpose |
|-------|---------|
| `_ACE_PRO_START` | Load the first tool (smart skip if already loaded) |
| `_ACE_PRO_END`   | Unload the current tool (cutter + retraction) |
| `_ACE_PRO_CANCEL`| Unload the current tool (cutter + retraction) |

### Example for a Generic Klipper Printer

**In your `PRINT_START` macro** (after homing and bed heating):

```cfg
_ACE_PRO_START TOOL=0 EXTRUDER_TEMP={EXTRUDER_TEMP}
```

**In your `PRINT_END` macro** (after park moves, before turning off heaters):

```cfg
_ACE_PRO_END
```

**In your `CANCEL_PRINT` macro** (before turning off heaters):

```cfg
_ACE_PRO_CANCEL
```

### Example for Simple AF Printers

Add the following to the respective Simple AF hooks:

- In `_SAF_START_PRINT_BEFORE_LINE_PURGE` (or wherever your start sequence is):
  ```
  _ACE_PRO_START TOOL=0 EXTRUDER_TEMP={EXTRUDER_TEMP}
  ```
- In `_SAF_END_PRINT_START`:
  ```
  _ACE_PRO_END
  ```
- In `_SAF_ON_CANCEL`:
  ```
  _ACE_PRO_CANCEL
  ```

> **Note:** The `_ACE_PRO_START` macro automatically checks if the requested tool is already loaded and physically present at the nozzle. If so, it skips the reload – saving time on print restarts.

---

## 🔌 Slicer Setup (OrcaSlicer)

To make ACE Pro work with your prints, you need to call the hook macros from your slicer’s start and end G‑code.

### Generic Klipper Printer

**Machine Start G‑code**:

```
_ACE_PRO_START TOOL=0 EXTRUDER_TEMP=[nozzle_temperature_initial_layer]
G28
M190 S[bed_temperature_initial_layer]
BED_MESH_CALIBRATE ADAPTIVE=1
```

**Machine End G‑code**:

```
_ACE_PRO_END
```

### Simple AF Printers

If you already have a `PRINT_START` macro that calls Simple AF hooks, just insert `_ACE_PRO_START` inside that macro as shown above. Then your slicer only needs to call `PRINT_START` with the usual parameters.

**Orca Slicer End G‑code** (still just `PRINT_END` if your macro includes `_ACE_PRO_END`).

---

## 🧪 Usage & Commands

All standard `T<n>` commands work and trigger a full tool change sequence. Additional commands are available for manual control.

| Command | Description |
|---------|-------------|
| `ACE_GET_STATUS` | Show ACE status (temperature, slots, dryer) |
| `ACE_QUERY_SLOTS` | List all slots with material/color information |
| `ACE_CHANGE_TOOL TOOL=<n>` | Change to tool `n` (0‑11 for three units) |
| `ACE_FEED T=<tool> LENGTH=<mm>` | Feed filament from a specific tool |
| `ACE_RETRACT T=<tool> LENGTH=<mm>` | Retract filament from a specific tool |
| `ACE_ENABLE_ENDLESS_SPOOL` / `ACE_DISABLE_ENDLESS_SPOOL` | Enable/disable automatic spool swapping on runout |
| `ACE_SET_ENDLESS_SPOOL_MODE MODE=exact\|material\|next` | Set match mode |
| `SERVO_TEST ANGLE=90` | Test the poop basket servo |

For a full list, see [example_cmds.txt](example_cmds.txt) (provided in the repository).

---

## ♻️ Endless Spool

When a filament runout is detected, Endless Spool automatically searches for a compatible spool and switches to it, allowing continuous printing.

### Match Modes

- **`exact`** (default) – requires matching material **and** RGB color.
- **`material`** – requires matching material only (color ignored).
- **`next`** – takes the first `ready` spool in round‑robin order (material/color ignored).

### Commands

```
ACE_ENABLE_ENDLESS_SPOOL
ACE_DISABLE_ENDLESS_SPOOL
ACE_SET_ENDLESS_SPOOL_MODE MODE=exact
ACE_GET_ENDLESS_SPOOL_MODE
```

### Safety: Unknown Materials

If a spool has no material label (e.g., non‑RFID, not manually set), it is marked as `Unknown`. Unknown materials **never** match each other – this prevents accidentally mixing incompatible materials. Always label your spools with `ACE_SET_SLOT` to enable safe endless spool.

---

## 🔌 Connection Supervision

Monitors ACE connection stability and can pause prints if the connection becomes unstable (6+ reconnects in 3 minutes). This feature is enabled by default.

To disable it:

```ini
[ace]
ace_connection_supervision: False
```

Use `ACE_GET_CONNECTION_STATUS` to see per‑instance stability details.

---

## 🖥️ KlipperScreen Panel (Optional)

A dedicated panel for KlipperScreen is included. It provides:

- Endless spool toggle and match mode selection
- Instance cycling (if multiple ACE units)
- Slot configuration (material, color, temperature)
- Load/unload controls, feed assist, RFID sync toggle
- Dryer controls

### Installation

The installer can optionally link the panel. If you installed manually:

```bash
ln -sf ~/acepro-any-klipper/KlipperScreen/acepro.py ~/KlipperScreen/panels/acepro.py
```

Then add the panel to your KlipperScreen menu (e.g., `main_menu.conf`):

```
[menu __main acepro]
name: ACE Pro
icon: settings
panel: acepro

[menu __print acepro]
name: ACE Pro
icon: settings
panel: acepro
```

Restart KlipperScreen (`sudo systemctl restart KlipperScreen`).

---

## 🔧 Troubleshooting

### “UNSOLICITED” messages in console

Normal after a reconnect – the module cleans up old responses. If frequent, check your USB cable and power.

### “High‑priority queue full”

Transient condition. Restart Klipper or power‑cycle the ACE unit if it persists.

### Spool does not wind tightly during retraction

Lower `retract_speed` in `acepro_setting.cfg` (try 30 mm/s instead of 50). This gives the spool more time to follow.

### Tool change fails with “path blocked”

Check sensor states with `ACE_DEBUG_SENSORS`. Ensure the toolhead sensor is clear and filament path is free. Use `ACE_CHANGE_TOOL TOOL=-1` to force an unload.

### No tool loaded after print start

Verify `_ACE_PRO_START` is called correctly and that ACE Pro is enabled (the virtual pin `ACE_Pro` should be 1). The macro prints console messages for debugging.

---

## 🙏 Credits & License

This project builds upon the excellent work of:

- [Kobra-S1/ACEPRO] (https://github.com/Kobra-S1/ACEPRO)
- [szkrisz/ACEPROSV08](https://github.com/szkrisz/ACEPROSV08)
- [utkabobr/DuckACE](https://github.com/utkabobr/DuckACE)
- [agrloki/ValgACE](https://github.com/agrloki/ValgACE)

This fork focuses on making the driver work with **any** Klipper printer, with an easy installer and simplified configuration.

**License:** GNU General Public License v3.0

---

**Happy printing!** 🖨️


UPDATING THE GITHUB
```
Erase the acepro-any-klipper:

rm -rf ~/acepro-any-klipper

After follow the install process
