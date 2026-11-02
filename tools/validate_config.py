#!/usr/bin/env python3
"""Check a Klipper config tree before Klipper is restarted.

Used by installer.sh (--check and the install step) and runnable by hand:

    python3 tools/validate_config.py ~/printer_data/config/printer.cfg [--profile saf|klipper|kalico]

What it checks (it never changes anything):
  * every [include ...] exists (wildcards may match nothing)
  * every G-code template is valid Jinja (same delimiters Klipper uses)
  * the same macro defined in more than one file (shown as a note: the later file wins)
  * servo_enable and the [servo servo_wipe] section agree
  * Kalico/Simple AF: heaters and pid_profile sections that have no "control:" line

Exit code: 0 = no errors (warnings are fine), 1 = at least one error.
It needs Python 3.6+; Jinja2 is used when installed (Klipper's own Python has it).
"""
import argparse
import configparser
import glob
import os
import re
import sys

try:
    import jinja2
except ImportError:  # the Jinja check is skipped, everything else still runs
    jinja2 = None

AUTOSAVE_MARK = "#*# <---------------------- SAVE_CONFIG ---------------------->"


class Result:
    def __init__(self):
        self.errors, self.warnings, self.notes = [], [], []


def read_config_lines(path):
    """Return the lines of a config file with the SAVE_CONFIG block un-commented."""
    out, in_auto = [], False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.strip() == AUTOSAVE_MARK:
                in_auto = True
                continue
            if in_auto and line.startswith("#*#"):
                line = line[4:] if line.startswith("#*# ") else line[3:]
            out.append(line)
    return out


def collect(path, res, seen=None, depth=0):
    """Follow [include] lines. Yield (file, section, option, value, first_line_no)."""
    seen = seen if seen is not None else set()
    real = os.path.realpath(path)
    if real in seen or depth > 20:
        return []
    seen.add(real)
    items = []
    lines = read_config_lines(path)
    base = os.path.dirname(path)
    section = None
    cur = None  # (option, [value lines], line_no)

    def flush():
        nonlocal cur
        if cur and section is not None:
            val = "\n".join(cur[1])
            if cur[0] not in ("gcode", "description"):     # inline comments, like Klipper does
                val = re.sub(r"\s+[#;].*$", "", val).strip()
            items.append((path, section, cur[0], val, cur[2]))
        cur = None

    for no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped[0] in "#;":
            if cur and line[:1] in " \t":      # a comment inside a multi-line value
                cur[1].append(line)
            continue
        m = re.match(r"^\[(.+?)\]\s*(?:[#;].*)?$", line)
        if m and line[:1] not in " \t":
            flush()
            name = m.group(1).strip()
            if name.startswith("include "):
                spec = name[len("include "):].strip()
                target = os.path.join(base, os.path.expanduser(spec))
                hits = sorted(glob.glob(target))
                if not hits and not glob.has_magic(target):
                    res.errors.append("%s:%d  [include %s] does not exist" % (path, no, spec))
                for h in hits:
                    items.extend(collect(h, res, seen, depth + 1))
                section = None
            else:
                section = name
                items.append((path, section, None, None, no))
            continue
        if line[:1] in " \t" and cur:
            cur[1].append(line)
            continue
        m = re.match(r"^([^:=\s][^:=]*?)\s*[:=]\s*(.*)$", line)
        if m and section is not None:
            flush()
            cur = (m.group(1).strip(), [m.group(2)], no)
    flush()
    return items


def check_autosave(path, res):
    """Text below the SAVE_CONFIG marker that is not part of the block breaks the saved values."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return
    marker = next((i for i, l in enumerate(lines) if l.strip() == AUTOSAVE_MARK), None)
    if marker is None:
        return
    for no, line in enumerate(lines[marker + 1:], marker + 2):
        if line.strip() and not line.startswith("#*#"):
            res.errors.append("%s:%d  this line is BELOW the SAVE_CONFIG block, where Klipper ignores the saved values "
                              "(heater PID, offsets ...). Move it above the line '#*# <--- SAVE_CONFIG --->'." % (path, no))
            return


def check_jinja(items, res):
    if jinja2 is None:
        res.notes.append("Jinja2 not installed: G-code templates were not syntax-checked")
        return
    env = jinja2.Environment("{%", "%}", "{", "}", extensions=["jinja2.ext.do"])
    for path, section, opt, val, no in items:
        if opt is None or val is None:
            continue
        if not (section.startswith("gcode_macro") or section.startswith("delayed_gcode")):
            continue
        if opt != "gcode" and not opt.startswith("description"):
            continue
        # Klipper's config reader drops ' # comment' tails before it builds the template
        val = "\n".join(re.sub(r"\s+[#;].*$", "", l) for l in val.split("\n"))
        try:
            env.parse(val)
        except jinja2.TemplateSyntaxError as exc:
            res.errors.append("%s:%d  [%s] %s: template error: %s" % (path, no, section, opt, exc.message))


def check_duplicates(items, res):
    where = {}
    for path, section, opt, val, no in items:
        if opt is None and section.startswith("gcode_macro"):
            where.setdefault(section, []).append(path)
    for section, files in sorted(where.items()):
        uniq = []
        for f in files:
            if f not in uniq:
                uniq.append(f)
        if len(uniq) > 1:
            names = ", ".join(os.path.basename(f) for f in uniq)
            res.notes.append("[%s] is defined in several files (%s). The one loaded last wins." % (section, names))


def merged(items):
    cfg = {}
    for path, section, opt, val, no in items:
        d = cfg.setdefault(section, {})
        if opt is not None:
            d[opt] = val
    return cfg


def check_consistency(cfg, res, profile):
    vars_ = cfg.get("gcode_macro _ACE_VARS", {})
    en = vars_.get("variable_servo_enable")
    if en is not None:
        want = en.strip().lower() == "true"
        have = "servo servo_wipe" in cfg
        if want and not have:
            res.errors.append("_ACE_VARS has variable_servo_enable: True but there is no [servo servo_wipe] "
                              "(acepro_servo.cfg missing?). Set it to False if you have no servo.")
        if have and not want:
            res.warnings.append("[servo servo_wipe] is defined but variable_servo_enable is False")
    if "ace" not in cfg:
        res.errors.append("There is no [ace] section: acepro_setting.cfg is not included")
    nozzle = [s for s in cfg if s in ("filament_switch_sensor filament_runout_nozzle",
                                      "filament_tracker filament_runout_nozzle")]
    if not nozzle:
        res.errors.append("No toolhead filament sensor (filament_runout_nozzle). The ACE driver needs one.")
    if vars_.get("variable_positions_confirmed", "True").strip().lower() == "false":
        res.warnings.append("Positions are still placeholders (variable_positions_confirmed: False). "
                            "Cutter, poop bucket and wipe moves will stop until you measure them.")
    if profile in ("kalico", "saf"):
        for s, opts in cfg.items():
            kind = s.split(" ")[0]
            if kind == "pid_profile" and "control" not in opts:
                res.errors.append("[%s] has no control: line. Kalico stops with \"control has to be specified\"." % s)
            elif (s in ("heater_bed", "extruder") or re.match(r"^extruder\d+$", s) or kind == "heater_generic") \
                    and "heater_pin" in opts and "control" not in opts and "pid_profile" not in " ".join(cfg):
                res.warnings.append("[%s] has no control: line. Kalico needs one (watermark, pid, or mpc)." % s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("printer_cfg")
    ap.add_argument("--profile", choices=["klipper", "kalico", "saf"], default="klipper")
    args = ap.parse_args()
    res = Result()
    if not os.path.isfile(args.printer_cfg):
        print("ERROR: %s not found" % args.printer_cfg)
        return 1
    items = collect(args.printer_cfg, res)
    check_autosave(args.printer_cfg, res)
    check_jinja(items, res)
    check_duplicates(items, res)
    check_consistency(merged(items), res, args.profile)
    for n in res.notes:
        print("note:    " + n)
    for w in res.warnings:
        print("warning: " + w)
    for e in res.errors:
        print("ERROR:   " + e)
    print("%d error(s), %d warning(s)" % (len(res.errors), len(res.warnings)))
    return 1 if res.errors else 0


if __name__ == "__main__":
    sys.exit(main())
