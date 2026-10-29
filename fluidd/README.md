# Fluidd ACE Pro panel

Fluidd v1.37.7 with two additions for this driver:

- **ACE Pro card** on the dashboard: every unit and slot (colour, material, temperature, RFID),
  load/unload, feed/retract, slot editing, dryer, endless spool and ACE on/off.
- **Spool picker at print start:** pressing Print (file browser) or Re-print shows "Choose ACE spools".
  Each filament in the file gets its best loaded spool (same material, closest colour) and you can
  change any of them. Fluidd then sends `ACE_SET_TOOL_MAP MAP=… FILE=…` and starts the print;
  the map applies to that print only.

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
