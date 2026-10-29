# Fluidd ACE Pro panel

Fluidd v1.37.7 with an ACE Pro panel for this driver:

- **ACE Pro card** on the dashboard in four layouts (cards, compact strip, spool rack, table): every unit
  and slot (colour, material, temperature, RFID), load/unload, feed/retract, slot editing, tool-change
  progress, dryer with material presets, endless spool (match mode and a takeover order per tool) and ACE on/off.
- **ACE Pro page** (side menu, or `#/ace`) with health and counters, the endless spool order and cutter tests.
- **Cutter wizard** to find `cut_full_x`, and **health and counters** (tool changes, cuts, purged filament).
- **Spool picker at print start:** pressing Print (file browser) or Re-print shows "Choose ACE spools".
  Each filament in the file gets the loaded spool with the closest colour (the filament type breaks ties);
  you can change any of them, drag to swap, use the map view, save a mapping, or dry the spools first.
  Fluidd then sends `ACE_SET_TOOL_MAP MAP=… FILE=…` and starts the print; the map applies to that print only.

The counters and endless spool order need the driver and `config/acepro.cfg` from this repo.

## Install the ready-made build

1. Back up your current Fluidd: `mv ~/fluidd ~/fluidd_backup`
2. `mkdir ~/fluidd && unzip fluidd-v1.37.7-acepro.zip -d ~/fluidd`
3. Copy your settings back: `cp ~/fluidd_backup/config.json ~/fluidd/` (if it exists)
4. Reload Fluidd in the browser (Cmd/Ctrl+Shift+R) and add the **ACE Pro** card from the
   dashboard layout editor if it isn't shown.

Check the download: `sha256sum -c fluidd-v1.37.7-acepro.zip.sha256`

## Build it yourself

```
git clone --branch v1.37.7 https://github.com/fluidd-core/fluidd
cd fluidd && git apply ../fluidd-acepro.patch
pnpm install && pnpm run build      # output in dist/
```

The card expects the endless spool switch as `[output_pin endless_spool]` and the ACE switch as
`[output_pin ACE_Pro]`, as in `config/acepro_setting.cfg`.
