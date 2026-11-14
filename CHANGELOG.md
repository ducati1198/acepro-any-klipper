# Changelog

## 1.1.2 (OrcaSlicer plugin 0.7.2)

- **OrcaSlicer plugin 0.7.2 (`orca_plugin/spool_toolhead_mapper.py`).** The `FILE=` part of `WM_SET_TOOL_MAP` / `ACE_SET_TOOL_MAP` now holds only the file name, not the full folder path Orca gives. Fluidd and the macro compare file names, so with a full path your "Choose toolheads" choice in Fluidd was always overwritten by Orca's map; now it is kept. The slicing step also writes lines to `~/.spool_toolhead_mapper.log` (started, skipped, what it wrote). 3 new tests.

## 1.1.1 (OrcaSlicer plugin 0.7.1)

- **`orca_plugin/spool_toolhead_mapper.py` 0.7.1** (same plugin as in wm-ultra-fluidd-acepro-panel 1.7.8). An address box per printer preset (Orca did not always give the plugin the print host), quote marks removed from the host, the panel notices a printer switch and filament changes, reads the printer again every 30 seconds, a `printer_kind` setting (auto, wm, ace), a status line and a log file (`~/.spool_toolhead_mapper.log`) for troubleshooting. A printer with both the ACE driver and the WonderMaker toolhead sensors is shown as the four toolheads; ACE-only printers such as the K1 are unchanged. The file must keep the name `spool_toolhead_mapper.py` (a dot or space in the name stops Orca from activating it). New test `tests/test_orca_plugin.py` (36 checks).

## 1.1.0 (safer installs, uninstall, doctor, position wizard)

- **Spoolman: link a SKU with `MAP_SKU`.** `MAP_SKU SKU=<sku> ID=<spool id>` and `UNMAP_SKU SKU=<sku>` save the link in `variables.cfg`, so you no longer edit the macro. The spool lookup, the messages (now in English) and the manual lock are otherwise as before. Ported from upstream Kobra-S1/ACEPRO. **After updating:** the old built-in SKU table is gone, so run `MAP_SKU` once for each SKU you used.
- **Simple AF hooks: no `ZERO_OUT_SERVO` in the heating nozzle (start and end), cancel, filament runout and nozzle wipe hooks.** The template no longer adds it there. Lines already in your own file stay as they are.
- **Fixes.** `--update` saved "no servo" in `acepro-install.conf` for every install; it now reads what is installed (servo, cutter, poop bucket). The config check no longer crashes on a broken symlink include; it reports an error. The unused `variable_cut_retract_distance` is removed.
- **Pause no longer leaves a blob.** The nozzle used to sit on the print for about 2 s while the servo was zeroed (twice, 0.8 s each) before it retracted and lifted. Now the pause retracts and lifts in one move first (`pause_zhop`, 2 mm, 0 = off), then zeroes the servo. In the Simple AF hook the order is `_ACE_ON_PAUSE`, then `ZERO_OUT_SERVO`; the standalone `PAUSE` does the same. The CFS chute variant is not changed.
- **Software Updates runs the installer.** The `acepro` entry now has an `install_script` (`tools/post-update.sh`). After you press Update, Moonraker runs `./installer.sh --update --auto`: new `--auto` flag, no questions, only with `--update`, no restart (Moonraker restarts Klipper), refuses during a print, backup first. It also puts the Fluidd ACE panel back when a Fluidd update removed it (the installer notes the installed panel build in `~/fluidd/.acepro-panel`). Older entries get the line on the next `--update`.
- **Tool change progress shows the real steps.** The driver reports the step that is running (`ACE_SET_PHASE`, `toolchange_phase` and `toolchange_steps` in the status) and the Fluidd card shows them as a bar plus a checklist (Heat, Cut, Retract, Load, Purge, Wipe). An unload lists only its own steps; a wipe that is switched off is left out. The Fluidd build is rebuilt, with new file names so a browser's cached copy is not used.
- **Unload buttons use `UNLOAD_TOOL`.** The Unload buttons in the Fluidd panel and in KlipperScreen now run `UNLOAD_TOOL` (retract, park, motors off) instead of `TR`. The ready-made Fluidd build is rebuilt with the change; the SHA256 file is updated.
- **Unload no longer grinds the filament.** After the cut and the move to the chute/wiper, the ACE started pulling while the extruder had not yet taken hold (the extruder retract was still queued behind those moves). The driver now waits for the cut and chute move to finish, hands the extruder retract to the stepper at once, and waits 0.25 s before the ACE starts pulling.
- **Resume no longer leaves a string.** After the resume purge and wipe the macro used to push out 0.5 mm of extra prime and Simple AF added its 1.0 mm unretract, right before the head moved back to the part. Now the nozzle is retracted after the wipe (`resume_post_wipe_retract`, 1.0 mm, counted on top of Simple AF's unretract) and `resume_extra_prime` is 0 by default. The retract before the purge has its own setting, `resume_pre_purge_retract` (0.5 mm). The old `resume_post_wipe_retract` was applied before the purge, not after the wipe. If your first line on the part looks thin, lower `resume_post_wipe_retract` to 0.5; if you still see a string, raise it to 1.5.
- **Fixes from a review of the config files.**
  - `min_zhop` and `allow_unhomed_zhop` now work (the Z hop before a tool change was fixed at 4 mm and 2 mm). New `zhop_lift` setting. With Z not homed the hop is skipped instead of failing.
  - `DISABLE_FILAMENT_NOZZLE` said "ENABLING". The standalone `RESUME` waited `servo_deploy_delay` instead of `servo_retract_delay` after retracting the servo. `SERVO_TEST` ignored `servo_name`. `_UNLOAD_TOOL_PRINT` forced absolute extrusion (`M82`); it now restores the saved state.
  - `TO_BLADE` and the `TO_FRONT_OF_THROW_BLADE` macros check `positions_confirmed` like the other cutter and bucket moves.
  - New settings instead of fixed values: `wipe_zigzag_amp`, `load_temp`, `unload_min_temp`, `unload_heat_temp`, `startup_cool_temp`, `purge_fallback_temp`. If your file has no such line the old value is used.
  - Smaller: no 1 s wait in `DEPLOY_SERVO_AT_THROW` without a servo; unused variable removed from `MY_START_PRINT`; about 240 lines of commented-out old code removed; wrong file name and the `detection_length` comment corrected.
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
- **Fluidd macro category:** the installer puts the ACE macros (not the hidden `_` ones) into a Fluidd category called ACEPRO MACRO, hot pink. Macros you already sorted stay where they are. Display setting only (Moonraker database); saved first, `--uninstall` removes it, `--undo` puts the old settings back.
- **Optional CFS purge chute variant** in `variants/cfs-chute/` (K1 Max, **not tested on any K1 series printer, use at your own risk**, not installed by the installer, nothing else changed). Positions start locked. See its README and section 15 of the main README.
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
