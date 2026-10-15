# ACE Pro Panel for Fluidd

An ACE Pro dashboard card for [Fluidd](https://github.com/fluidd-core/fluidd), designed
for the [acepro-any-klipper](https://github.com/ducati1198/acepro-any-klipper)
Klipper driver (Anycubic ACE / ACE Pro multi-material units).

![Panel screenshot](docs/panel.png)

## Features

- **Slot grid** — one spool per slot, colored from the driver data. Click a spool to
  load it (`T<n>`); click the pencil to edit material type and color
  (persisted via `ACE_SET_SLOT`).
- **Filament path** — live view of the filament route
  `ACE -> SPLITTER -> Encoder -> Nozzle`, driven by your filament sensors:
  - green filled dot — sensor sees filament;
  - hollow red dot — sensor is present but reports no filament;
  - the section is **hidden automatically** when the matching sensor does not
    exist in the printer config, so the path adapts to your hardware.
- **Jam indicator** — the encoder ring turns red when filament is at the nozzle
  but not at the encoder (jam or break between them).
- **Feed assist toggle** — one-click `ACE_ENABLE_FEED_ASSIST T=` /
  `ACE_DISABLE_FEED_ASSIST T=` (native driver commands).
- **Dryer dialog** — chamber temperature, DRYING/IDLE state with remaining time,
  temperature slider (50–65 °C, step 5) and duration slider (30–240 min, step 30).
- Service actions: load all slots, full unload, reconnect, request status.

## Requirements

- Klipper + Moonraker with the `acepro-any-klipper` driver installed and working
  (`printer.ace` / `printer.ace_instance_<n>` objects visible in the API).
- ~3.5 GB free disk space for the build. Node.js >= 18 is installed
  automatically if missing.

## Prebuilt build (no compilation needed)

If you don't want to install Node.js and build from source, grab the prebuilt
archive from the
[latest release](https://github.com/sanakess/fluidd-ace-panel/releases/latest)
and unpack it over your Fluidd webroot:

```bash
curl -L -o fluidd-ace-v1.1.tar.gz https://github.com/sanakess/fluidd-ace-panel/releases/download/v1.1/fluidd-ace-v1.1.tar.gz
sudo rm -rf /usr/share/fluidd/*        # adjust to your webroot
sudo tar xzf fluidd-ace.tar.gz -C /usr/share/fluidd
```

Hard-reload the browser (Ctrl+Shift+R) afterwards. To build from source
instead (e.g. to track a newer Fluidd version), follow the steps below.

## Installation

Run **on the Klipper host** (SSH into your Pi, e.g. `ssh pi@<printer-ip>`):

```bash
git clone https://github.com/sanakess/fluidd-ace-panel.git
cd fluidd-ace-panel
bash install.sh
```

or as a one-liner — the script fetches the panel sources by itself:

```bash
curl -fsSL https://raw.githubusercontent.com/sanakess/fluidd-ace-panel/main/install.sh | bash
```

The script is self-sufficient. It:

1. checks that Moonraker is up and the `acepro-any-klipper` driver is visible
   in the API (`FORCE=1` to skip),
2. installs Node.js 22 LTS and pnpm if they are missing,
3. adds a temporary swap file on low-memory hosts (always removed afterwards),
4. clones a fresh Fluidd, copies the panel, patches Fluidd and builds it,
5. backs up the current webroot, deploys, verifies the deployed bundle and
   rolls back on failure.

Webroots are auto-detected (`/usr/share/fluidd`, `/var/www/fluidd`, `/opt/fluidd`,
`/home/pi/fluidd`); the previous version is kept as `webroot.bak-ace-<timestamp>`.

Options (environment variables):

```bash
# custom webroot
WEBROOT=/home/pi/fluidd bash install.sh

# keep the built repository for debugging
KEEP_REPO=1 bash install.sh

# skip the ACE driver preflight check
FORCE=1 bash install.sh

# never create a temporary swap file
NO_SWAP=1 bash install.sh

# Moonraker on a non-default URL
MOONRAKER_URL=http://192.168.1.10:7125 bash install.sh
```

The build needs ~3.5 GB of free disk (never in `/tmp` — it is often a small
tmpfs) and passwordless `sudo` for installing Node.js and the temporary swap.

After the install, reload Fluidd with **Ctrl+Shift+R**. If the card does not
appear, clear the service worker (DevTools -> Application -> Storage ->
"Clear site data") and reload once more.

The card shows up automatically on the dashboard when the ACE driver is present,
and hides itself when the ACE is disconnected.

## Sensor naming (auto-detection)

Path nodes are matched by substring, tolerantly, against the objects in your
Klipper config:

| Node     | Matches object names containing      | Typical config section |
|----------|--------------------------------------|------------------------|
| SPLITTER | `runout_rdm`                         | `filament_switch_sensor filament_runout_rdm` |
| Encoder  | `ace_encoder` or `tracker`           | `filament_motion_sensor ace_encoder` |
| Nozzle   | `runout_nozzle`                      | `filament_switch_sensor filament_runout_nozzle` |

If a sensor is missing, its node (and the line leading to it) is simply not
rendered — e.g. a printer without the splitter sensor gets
`ACE -> Encoder -> Nozzle`, and a printer with only a runout sensor gets a
single `ACE -> Nozzle` hop. Names like `filament_runout_rdm_2` are matched too.

## Updating

Run `bash install.sh` again — it always builds from a fresh Fluidd clone and
deploys over the existing webroot (with a fresh backup).

## Uninstalling

Restore the pre-install backup:

```bash
rm -rf /usr/share/fluidd
mv /usr/share/fluidd.bak-ace-<timestamp> /usr/share/fluidd
```

(or redeploy an official Fluidd build from
[github.com/fluidd-core/fluidd/releases](https://github.com/fluidd-core/fluidd/releases)).

## Troubleshooting

- **Old UI after install** — hard reload; if that does not help, clear the
  service worker as described above.
- **`anchor ... matched 0 time(s)` during patching** — your Fluidd checkout
  differs from upstream; update the anchors in `apply_fluidd_ace.py` manually.
- **Card not visible at all** — confirm the driver objects exist, e.g.
  `curl localhost:7125/printer/objects/list | grep ace`.
- **Using OctoEverywhere?** It injects its own files (`/oe` + a script tag)
  into the Fluidd webroot. Updating Fluidd removes them; the OctoEverywhere
  service re-injects them automatically within a minute or two. If remote
  access stays broken, re-run the OctoEverywhere installer.

## License

GPL-3.0 — this is a derivative work of Fluidd (GPLv3).
