# CFS purge chute variant (K1 Max) — NOT TESTED on any K1 series printer

> **⚠️ Use at your own risk.** This project is provided "as is", without warranty of any kind. The author and contributors are **not responsible for any damage** to your printer, ACE Pro units, electronics, prints or anything else, or for any injury or loss, caused by using or misusing these files. See the [Disclaimer](../../README.md#disclaimer-use-at-your-own-risk).

> ## ⚠️ Read this first: untested, use at your own risk
>
> This is a separate set of ACE Pro files for a **K1 Max with the factory CFS purge chute** instead of a servo poop bucket.
>
> - **It has NOT been tested on any K1 series printer** (K1, K1C, K1 Max or K1 SE). The author does not own the CFS purge chute, its extruder or the cutter block, so none of this could be tried on that hardware.
> - The positions and settings come from the author's own configuration and from the reference project [swilsonnc/ACEPROK1Max](https://github.com/swilsonnc/ACEPROK1Max). They have **not** been verified on a real CFS chute, extruder or cutter block.
> - It has not been run through this repository's installer either.
>
> **Use it entirely at your own risk.** The author and contributors are **not responsible for any damage** to your printer, toolhead, cutter, chute, hotend, bed, filament or anything else, or for any injury or loss, that results from using these files. They come with no warranty (see the GPL-3.0 licence).
>
> ### ⚠️ Caution: check before you run anything
>
> - **Check your printer's specs yourself.** Confirm your axis limits (`position_max`), where your chute, flap and cutter block really are, your sensor pins and your toolhead before you trust any number in these files.
> - Every position is a placeholder until **you** have measured it on **your** machine. They start locked (`variable_positions_confirmed: False`) on purpose. Do not set it to True until you have checked them.
> - **Test in small steps**: one move at a time, slowly, with the nozzle cold and no filament loaded first. Keep your hand on the power switch or emergency stop. Never leave the printer unattended while testing.
> - A wrong position can crash the toolhead into the chute, the cutter or the frame. If anything looks wrong, stop and power off.

It is optional. Nothing in `config/`, the installer, the tests or the other docs depends on it, and the installer never installs or changes it.

## What it is

The normal install (`config/acepro*.cfg`) assumes a servo-controlled poop basket. This variant swaps that for the CFS chute at the back of a K1 Max:

1. After the cut, the head goes to **Y287**, then creeps into the chute at 700 mm/min, so the nozzle does not clip the chute lip.
2. It purges, then **retracts 2 mm** so the nozzle does not ooze across the flap.
3. **`HIT_PURGE_CHUTE`** moves the head back and forth (10 times) to knock off stuck filament.
4. **`WIPE_ON_CHUTE_FLAP`** drags the nozzle over the factory silicone flap (X199 to X209, 2 passes).
5. It **backs out slowly**: along the rear wall to the entry X, then out in Y at 700 mm/min.
6. The usual nozzle wipe runs, then the 2 mm is pushed back.

No servo is used. The bed is lifted to a clearance height (60 mm) before crossing the back of the printer.

## Files

| File | Purpose |
|---|---|
| `cfs_acepro.cfg` | Main file. Sensors, `TO_THROW_POSITION`, `CUT_TIP`, `RESUME_NOZZLE_WIPE_SEQUENCE` and friends. |
| `cfs_acepro_setting.cfg` | The `[ace]` driver section, virtual pins, temperature sensors. |
| `cfs_acepro_macros.cfg` | `_ACE_VARS` (all positions), the post-toolchange purge, `HIT_PURGE_CHUTE`, `WIPE_ON_CHUTE_FLAP`. |
| `cfs_acepro_printer_macros.cfg` | `PAUSE`, `RESUME`, `MY_START_PRINT`, purge macros. |
| `cfs_cut_calibrate.cfg` | Cutter calibration (`CUT_CAL_START`, `CUT_CAL_STEP`, `CUT_CAL_END`). |

## How to use it (by hand)

1. Install the driver with the normal `./installer.sh` first. That puts the driver links in Klipper and the normal ACE files in place.
2. Copy the five `cfs_*.cfg` files into your printer's config folder (next to `printer.cfg`).
3. In `printer.cfg`, change `[include acepro.cfg]` to `[include cfs_acepro.cfg]`. **Use one or the other, never both**: they define the same macros and sections, and Klipper would merge them.
4. Check or measure the positions below, then set `variable_positions_confirmed: True` in `cfs_acepro_macros.cfg`.
5. Change the three sensor pins in `cfs_acepro.cfg` if your wiring differs (marked `K1 Max pin`).
6. Restart Klipper.

**Careful with the installer afterwards.** It only knows the normal `acepro*.cfg` files. `./installer.sh --repair` and `--doctor` will say `[include acepro.cfg]` is missing and offer to add it back. Answer **no**, or you get both sets. `--update` and `--uninstall` do not touch the `cfs_*` files.

## Safety: positions start locked

This copy adds a lock that the original CFS files did not have. `variable_positions_confirmed` is **False**, and `CUT_TIP`, `TO_THROW_POSITION`, `HIT_PURGE_CHUTE`, `WIPE_ON_CHUTE_FLAP` and the post-toolchange purge stop with a message until you set it to **True**. Every position in the file is a K1 Max number.

## Positions (all K1 Max)

| What | Values | Where |
|---|---|---|
| Cutter block | X50 Y304 | `variable_cut_block_x/y` |
| Cutter start | X43 Y304 | `variable_cut_engage_x/y` |
| Cutter end (blade closed) | X32 Y304 | `variable_cut_full_x/y` |
| Chute | X180.5 Y303 | `variable_poop_x/y` |
| Slow approach | Y287, 700 mm/min | `variable_chute_approach_y`, `_speed` |
| Chute shakes | Y303 to Y295, 10 times | `variable_chute_hit_*` |
| Flap wipe | Y305.5 (limited to your axis maximum), X199 to X209, 2 passes, 3000 mm/min | `variable_flap_wipe_*` |
| Retract after purge | 2 mm at 500 mm/min (0 turns it off) | `variable_post_purge_retract`, `_speed` |
| Nozzle wipe | start X175 Y278, zigzag, 13 mm | `variable_wipe_*` |
| Clearance lift | Z60 | `variable_clearance_z_height` |

On the author's printer `position_max` on Y is 304, so the 305.5 flap wipe runs at Y304 there. Klipper refuses any move beyond your axis limits. Check yours.

## K1 and other printers

- **Nothing here has been tested on any K1 series printer.**
- **K1, K1C and other smaller printers:** the numbers above do not fit. The chute at Y303 is far beyond a 220 mm bed, so moves would be rejected. There are no verified values for them here. You would have to measure every position yourself. Keep the lock on until you have.
- **A K1 Max:** the CFS chute is factory hardware, so the chute and flap numbers may be close, but that has **not** been verified. The cutter position depends on where the cutter block is mounted, so measure it.
- Use `CUT_CAL_START` and `CUT_CAL_STEP` to find the cutter positions in small steps. Test `WIPE_ON_CHUTE_FLAP` and `HIT_PURGE_CHUTE` on their own, slowly, with the nozzle cold and nothing loaded, before a real tool change.

## How this differs from the main install

This is an older base (V3.0). Compared with `config/`, it does **not** have:

- the `ACE_Pro` switch behaviour for Simple AF pause and resume (`_ACE_ON_PAUSE`, `_ACE_ON_RESUME`)
- the Simple AF hooks file support
- hardware switches (`cutter_enable`, `poop_enable`, an optional servo file)
- the newer fixes made while building the installer

Changes made when this copy was added to the repository (compared with the files on the author's printer):

- `variable_positions_confirmed` and `_ACE_REQUIRE_POSITIONS` added (the lock above).
- `[servo servo_wipe]` commented out. This variant does not use it, and `PB14` is a K1 Max pin.
- Sensor pins marked as K1 Max pins.
- A header saying this is an untested variant.

Features added on top of the original CFS files by the author: `variable_chute_approach_y` slow approach, `WIPE_ON_CHUTE_FLAP`, the post-purge retract with matching push back, and the slow exit from the chute.

## Useful notes

- It needs your own `START_PRINT` macro (called by `MY_START_PRINT`). Simple AF users also need `_SAF_ACE_TOOL_LOAD` in their hooks (see the comment in `cfs_acepro_printer_macros.cfg`).
- Turn the new behaviours off one at a time to find a problem: `variable_post_purge_retract: 0`, `variable_flap_wipe_enable: False`, `variable_chute_approach_y: 0`, `variable_chute_hit_enable: False`.
- If the retract leaves a string on the flap, try a smaller value. If filament is short at the start of a print, check that the push back after the wipe ran.
- `variable_chute_approach_speed` is used for the approach and the exit. Raise it only after several clean tool changes.
- Heat stays on during these moves. Do not leave the printer unattended while testing.
- Set `variable_servo_enable: True` and uncomment `[servo servo_wipe]` only if you actually fit a servo, with your own pin.

## Credits

- [Kobra-S1/ACEPRO](https://github.com/Kobra-S1/ACEPRO), the original driver.
- [swilsonnc/ACEPROK1Max](https://github.com/swilsonnc/ACEPROK1Max), the reference K1 Max with CFS setup. The Y287 slow approach, the flap wipe positions and the retract after purge come from its `ace.cfg`.
- Files organised and maintained by Ducati_1198. License: GPL-3.0, see [`LICENSE`](../../LICENSE).
