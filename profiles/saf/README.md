# Simple AF profile

> **⚠️ Use at your own risk.** This project is provided "as is", without warranty of any kind. The author and contributors are **not responsible for any damage** to your printer, ACE Pro units, electronics, prints or anything else, or for any injury or loss, caused by using or misusing these files. See the [Disclaimer](../../README.md#disclaimer-use-at-your-own-risk).

What the installer does differently on Simple AF (Pellcorp):

- `PAUSE` and `RESUME` come with the shared `acepro_printer_macros.cfg` like on every profile. Simple AF's `client.cfg` defines them too; the file loaded last wins, and on Simple AF that is `client.cfg`, so the printer's own versions stay in charge. `my_saf_hooks.cfg` gets `_SAF_ON_PAUSE` / `_SAF_ON_RESUME`, which run the ACE steps only while the `ACE_Pro` switch is on.
- Puts every file in the main config folder (not a subfolder), so Simple AF's `pellcorp-overrides`
  backup keeps them across `installer.sh --update`.
- Never edits `moonraker.conf`, `client.cfg`, `start_end.cfg` or other files Simple AF owns.
- Writes or UPDATES `my_saf_hooks.cfg`: your own lines stay, the ACE lines are added at the top of each hook (`ZERO_OUT_SERVO` first, then the encoder line; in `_SAF_END_PRINT_START` the encoder line is first and `ZERO_OUT_SERVO` stays below it).
  The encoder lines are kept only if you have the encoder sensor. Hooks defined in another file are listed, not touched.
  Asks whether to add `[include my_saf_hooks.cfg]` to printer.cfg or leave that to you (Fluidd).
- The print start line is `MY_START_PRINT TOOL=... ` (it hands off to Simple AF's `START_PRINT`).
- After a Simple AF update run `./installer.sh --repair`. Simple AF only runs `git reset --hard` on its
  Klipper copy, so the links usually survive, but `--repair` checks them for you.
