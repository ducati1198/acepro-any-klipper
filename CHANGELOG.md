# Changelog

## 1.0.0 (installer for Klipper, Kalico and Simple AF)

- **One installer, three setups.** It asks Klipper, Kalico or Simple AF (and suggests one by looking at the Pi), then installs the right files. Profiles live in `profiles/`.
- **Plain questions with a reason and a safe default:** number of ACE units, toolhead / RDM / encoder sensor pins, servo poop basket, cutter, poop bucket, extras.
- **Safety:** every install saves a backup first (`--undo` restores it); the new files are checked before anything is written and again before Klipper restarts; a self-test runs after the restart.
- **Positions start locked.** The sample cutter / bucket / wipe positions come from a Creality K1 Max, so a new install blocks moves to them until you set `variable_positions_confirmed: True`.
- **Commands:** `--update` (keeps your values), `--check`, `--repair` (links and includes), `--undo`, `--dry-run`, `--support-bundle`.
- **Simple AF:** never edits `moonraker.conf`; puts files where its overrides backup finds them; writes the ACE hooks file only when you have no hooks of your own.
- **Servo is optional.** `[servo servo_wipe]` moved to `acepro_servo.cfg`; `servo_enable`, `cutter_enable` and `poop_enable` switch the matching macros off.
- **PAUSE / RESUME stay in `acepro_printer_macros.cfg`** for all profiles. On Simple AF, `client.cfg` loads later and its versions win.
- **Fix:** `PUSHOVER_ENCODER_SENSOR` is now defined (does nothing until you define your own), so a sensor alert no longer fails with "Unknown command" on a fresh install.
- **Fix:** removed the `SMART_TOOL` branch from `MY_START_PRINT`; the macro never existed.
- **Examples (not installed):** `examples/servo_wiper.cfg`, `examples/saf_hooks_example.cfg`.
- **Tests:** `bash tests/installer/run_tests.sh` runs the installer against fake folders.
