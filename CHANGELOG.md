# Changelog

## 1.1.0 (safer installs, uninstall, doctor, position wizard)

- **One ACE temperature sensor per unit.** With 1 unit you get `acepro_temp_1`, with 2 you also get `acepro_temp_2`, with 3 you get `acepro_temp_3`. The extra ones are commented out.
- **Refuses to run while a print is active** (printing or paused). No override. `--check`, `--support-bundle` and `--dry-run` still work.
- **Virtual-pin order warning.** If a file uses `virtual_pin:` before `[virtual_pins]` is loaded (Klipper: "Unknown pin chip name 'virtual_pin'"), the installer and the config check say so; the installer offers to add `[virtual_pins]` at the top of `printer.cfg` (saved first, only on yes).
- **ACE USB check.** Warns if no ACE shows up on USB, then carries on.
- **More folder layouts:** `printer_data` in another place, several Klipper instances (you pick one; service `klipper-N`), and Creality K1 native `/usr/data` (experimental, no systemd or sudo). Also checks sudo and the Klipper service name.
- **`--uninstall`** removes what the installer added (ACE files, driver links, KlipperScreen link and menu, include line, the ACE lines in `my_saf_hooks.cfg`). Your own lines stay. Saved first; `--undo` brings it back.
- **`--doctor`** finds problems (missing include, broken links, lines below SAVE_CONFIG, virtual-pin order, duplicate macros), explains them and offers a fix with a backup. Acts only on yes.
- **Import old values:** a fresh install searches earlier installs and backups, shows what differs, and asks which one to copy your values from.
- **Position wizard in Fluidd:** `ACE_SETUP_CUTTER` and `ACE_SETUP_BUCKET` walk you through the points; you jog the head, `ACE_SETUP_SAVE POINT=<name>` writes the X/Y into `acepro_macros.cfg` (no restart needed; the old file is kept as `acepro_macros.cfg.before-setup`), `ACE_SETUP_CONFIRM` unlocks the moves. Refused during a print.
- **`ACE_SELFTEST`:** read-only check of the driver, each unit's connection, temperatures, sensors, confirmed positions and the switches. Nothing moves.
- **Software Updates entry:** the installer adds `[update_manager acepro]` to `moonraker.conf` (saved first; on Simple AF it asks first because Simple AF may overwrite that file). It only downloads new code; run `./installer.sh --update` after.
- **"What changed" after `--update`:** the entries of this file newer than your installed version are shown.

## 1.0.0 (installer for Klipper, Kalico and Simple AF)

- **One installer, three setups.** It asks Klipper, Kalico or Simple AF (and suggests one by looking at the Pi), then installs the right files. Profiles live in `profiles/`.
- **Plain questions with a reason and a safe default:** number of ACE units, toolhead / RDM / encoder sensor pins, servo poop basket, cutter, poop bucket, extras.
- **Safety:** every install saves a backup first (`--undo` restores it); the new files are checked before anything is written and again before Klipper restarts; a self-test runs after the restart.
- **Positions start locked.** The sample cutter / bucket / wipe positions come from a Creality K1 Max, so a new install blocks moves to them until you set `variable_positions_confirmed: True`.
- **Commands:** `--update` (keeps your values), `--check`, `--repair` (links and includes), `--undo`, `--dry-run`, `--support-bundle`.
- **Simple AF:** never edits `moonraker.conf`; puts files where its overrides backup finds them; writes the ACE hooks file only when you have no hooks of your own.
- **Simple AF pause/resume follow the `ACE_Pro` switch** through `_SAF_ON_PAUSE` / `_SAF_ON_RESUME` → `_ACE_ON_PAUSE` / `_ACE_ON_RESUME`. Switch off = plain Simple AF. Simple AF's own PAUSE/RESUME stay in charge.
- **Simple AF hooks file is `my_saf_hooks.cfg`.** The installer asks whether to add its include line or leave that to you; an existing file is updated (`ZERO_OUT_SERVO` and the encoder line at the top of each hook, except `ZERO_OUT_SERVO` in `_SAF_END_PRINT_START`; your lines kept), the encoder lines are added or removed to match the sensor you chose.
- **Fix:** lines added to `printer.cfg` (`[force_move]`) now go above Klipper's SAVE_CONFIG block, not below it. Below it they broke the saved values (Kalico stopped with `pid_profile: 'control' has to be specified`). The config check now reports any text below that block.
- **Fix:** `[force_move]` is looked for in all your config files (Simple AF's `homing.cfg` already has it), so it is no longer added a second time. The config check no longer reports a false template error for ` # comment` tails inside a macro (Klipper drops them too).
- **Servo is optional.** `[servo servo_wipe]` moved to `acepro_servo.cfg`; `servo_enable`, `cutter_enable` and `poop_enable` switch the matching macros off.
- **PAUSE / RESUME stay in `acepro_printer_macros.cfg`** for all profiles. On Simple AF, `client.cfg` loads later and its versions win.
- **Fix:** `PUSHOVER_ENCODER_SENSOR` is now defined (does nothing until you define your own), so a sensor alert no longer fails with "Unknown command" on a fresh install.
- **Fix:** removed the `SMART_TOOL` branch from `MY_START_PRINT`; the macro never existed.
- **Examples (not installed):** `examples/servo_wiper.cfg`, `examples/saf_hooks_example.cfg`.
- **Tests:** `bash tests/installer/run_tests.sh` runs the installer against fake folders.
