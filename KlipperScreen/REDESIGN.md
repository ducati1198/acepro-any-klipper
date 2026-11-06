# ACE Pro screen redesign (test)

`acepro_redesign.py` is a new look for the KlipperScreen ACE Pro panel. It
sits next to the stock `acepro.py` and reuses its Klipper plumbing, so
`acepro.py` is unchanged and nothing installs it by default.

New in it: filament-path home screen, slot sheet with slot test, tool-change
progress, color picker (swatches, picker, typed hex), dryer presets and gauge,
status page (sensors, usage counters, blade-life bar), print check with tool
swaps, endless-spool takeover order, feed/retract/purge speeds, filament
position fixer, ACE2 firmware update, inventory reset.

Tested on a real 7" 600x1024 portrait screen. Other sizes (320x480 up to 1280x800, landscape and portrait) scale automatically and were checked in an offscreen simulation only, not on real hardware.

## Try it

    ln -sfn ~/acepro-any-klipper/KlipperScreen/acepro_redesign.py ~/KlipperScreen/panels/acepro.py
    sudo systemctl restart KlipperScreen

## Go back

    ln -sfn ~/acepro-any-klipper/KlipperScreen/acepro.py ~/KlipperScreen/panels/acepro.py
    sudo systemctl restart KlipperScreen
