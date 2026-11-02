# Simple AF profile

What the installer does differently on Simple AF (Pellcorp):

- `PAUSE` and `RESUME` come with the shared `acepro_printer_macros.cfg` like on every profile. Simple AF's `client.cfg` defines them too; the file loaded last wins, and on Simple AF that is `client.cfg`, so the printer's own versions stay in charge. The hooks file adds `_SAF_ON_PAUSE` / `_SAF_ON_RESUME`, which run the ACE steps only while the `ACE_Pro` switch is on.
- Puts every file in the main config folder (not a subfolder), so Simple AF's `pellcorp-overrides`
  backup keeps them across `installer.sh --update`.
- Never edits `moonraker.conf`, `client.cfg`, `start_end.cfg` or other files Simple AF owns.
- Writes `acepro_saf_hooks.cfg` only when you have none of the hook macros it defines. If you
  already have hooks it prints the lines to add (see `examples/saf_hooks_example.cfg`).
- The print start line is `MY_START_PRINT TOOL=... ` (it hands off to Simple AF's `START_PRINT`).
- After a Simple AF update run `./installer.sh --repair`. Simple AF only runs `git reset --hard` on its
  Klipper copy, so the links usually survive, but `--repair` checks them for you.
