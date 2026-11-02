# Simple AF profile

What the installer does differently on Simple AF (Pellcorp):

- Keeps Simple AF's `PAUSE` and `RESUME` (`client.cfg`). It does not install `acepro_pause_resume.cfg`.
- Puts every file in the main config folder (not a subfolder), so Simple AF's `pellcorp-overrides`
  backup keeps them across `installer.sh --update`.
- Never edits `moonraker.conf`, `client.cfg`, `start_end.cfg` or other files Simple AF owns.
- Writes `acepro_saf_hooks.cfg` only when you have none of the hook macros it defines. If you
  already have hooks it prints the lines to add (see `examples/saf_hooks_example.cfg`).
- The print start line is `MY_START_PRINT TOOL=... ` (it hands off to Simple AF's `START_PRINT`).
- After a Simple AF update run `./installer.sh --repair`. Simple AF only runs `git reset --hard` on its
  Klipper copy, so the links usually survive, but `--repair` checks them for you.
