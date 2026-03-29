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

### One‑Click Installer (Recommended)

```bash
cd ~
git clone -b dev https://github.com/ducati1198/acepro-any-klipper
cd acepro-any-klipper
chmod +x installer.sh
./installer.sh
