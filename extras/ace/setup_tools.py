"""Position wizard and self-test commands.

ACE_SETUP_SAVE   record the toolhead's current X/Y as one of the named positions and write it into
                 acepro_macros.cfg (and into the running macro, so no restart is needed)
ACE_SETUP_CONFIRM  set variable_positions_confirmed: True
ACE_SELFTEST     read-only health check; nothing moves, nothing is changed
"""

import os
import re

# name -> (X variable, Y variable), all in [gcode_macro _ACE_VARS]
POINTS = {
    "cut_block": ("cut_block_x", "cut_block_y"),
    "cut_engage": ("cut_engage_x", "cut_engage_y"),
    "cut_full": ("cut_full_x", "cut_full_y"),
    "poop": ("poop_x", "poop_y"),
    "osc_start": ("nozzle_osc_start_x", "nozzle_osc_start_y"),
    "osc_stop": ("nozzle_osc_stop_x", "nozzle_osc_stop_y"),
    "wipe_start": ("wipe_start_x", "wipe_start_y"),
}
VARS_SECTION = "gcode_macro _ACE_VARS"
HEADER = re.compile(r"^\[(.+?)\]\s*(?:[#;].*)?$")


def fmt(value):
    text = ("%.2f" % float(value)).rstrip("0").rstrip(".")
    return text or "0"


def set_variables_in_text(text, values):
    """Return text with variable_<name>: <value> replaced inside _ACE_VARS (comments after the value stay).

    values = {name: str}. Raises KeyError(name) if a variable is not in the section.
    """
    lines = text.split("\n")
    section = None
    todo = dict(values)
    for i, line in enumerate(lines):
        h = HEADER.match(line) if line[:1] == "[" else None
        if h:
            section = h.group(1).strip()
            continue
        if section != VARS_SECTION:
            continue
        m = re.match(r"^(variable_([A-Za-z0-9_]+))(\s*:\s*|\s*=\s*)([^#;\n]*?)(\s*(?:[#;].*)?)$", line)
        if m and m.group(2) in todo:
            keep_space = m.group(5) if m.group(5).strip() else ""
            pad = "  " if keep_space and not keep_space.startswith(" ") else ""
            lines[i] = "%s%s%s%s%s" % (m.group(1), m.group(3), todo.pop(m.group(2)), pad, keep_space)
    if todo:
        raise KeyError(", ".join(sorted(todo)))
    return "\n".join(lines)


def _macros_file(printer):
    cfg = printer.get_start_args().get("config_file", "")
    path = os.path.join(os.path.dirname(cfg), "acepro_macros.cfg")
    return path if os.path.isfile(path) else None


def _write_file(path, values):
    with open(path, encoding="utf-8", errors="surrogateescape") as fh:
        text = fh.read()
    new = set_variables_in_text(text, values)
    backup = path + ".before-setup"
    if not os.path.exists(backup):
        with open(backup, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(text)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(new)
    os.replace(tmp, path)


def _refuse_if_printing(printer, gcmd):
    ps = printer.lookup_object("print_stats", None)
    if ps is not None and ps.get_status(printer.get_reactor().monotonic()).get("state") in ("printing", "paused"):
        raise gcmd.error("ACE setup: not while a print is running or paused")


def make_commands(get_printer):
    def cmd_ACE_SETUP_SAVE(gcmd):
        """POINT=<name> saves the current X/Y. POINT=list shows the names."""
        printer = get_printer()
        point = gcmd.get("POINT", "list").lower()
        if point == "list" or point not in POINTS:
            gcmd.respond_info("ACE_SETUP_SAVE POINT=" + " | ".join(sorted(POINTS)))
            if point != "list":
                raise gcmd.error("ACE_SETUP_SAVE: unknown POINT '%s'" % point)
            return
        _refuse_if_printing(printer, gcmd)
        toolhead = printer.lookup_object("toolhead")
        homed = toolhead.get_status(printer.get_reactor().monotonic()).get("homed_axes", "")
        if "x" not in homed or "y" not in homed:
            raise gcmd.error("ACE_SETUP_SAVE: home X and Y first (G28 X Y)")
        pos = toolhead.get_position()
        vx, vy = POINTS[point]
        values = {vx: fmt(pos[0]), vy: fmt(pos[1])}
        path = _macros_file(printer)
        if path is None:
            raise gcmd.error("ACE_SETUP_SAVE: acepro_macros.cfg not found next to printer.cfg")
        try:
            _write_file(path, values)
        except KeyError as exc:
            raise gcmd.error("ACE_SETUP_SAVE: %s is not in _ACE_VARS of %s" % (exc, path))
        gcode = printer.lookup_object("gcode")
        for name, value in values.items():
            gcode.run_script_from_command("SET_GCODE_VARIABLE MACRO=_ACE_VARS VARIABLE=%s VALUE=%s" % (name, value))
        gcmd.respond_info("ACE setup: %s saved: X=%s Y=%s (written to %s)" % (point, values[vx], values[vy], os.path.basename(path)))

    def cmd_ACE_SETUP_CONFIRM(gcmd):
        printer = get_printer()
        _refuse_if_printing(printer, gcmd)
        path = _macros_file(printer)
        if path is None:
            raise gcmd.error("ACE_SETUP_CONFIRM: acepro_macros.cfg not found next to printer.cfg")
        _write_file(path, {"positions_confirmed": "True"})
        printer.lookup_object("gcode").run_script_from_command(
            "SET_GCODE_VARIABLE MACRO=_ACE_VARS VARIABLE=positions_confirmed VALUE=True")
        gcmd.respond_info("ACE setup: positions confirmed. Cutter, bucket and wipe moves are allowed now.")

    def cmd_ACE_SELFTEST(gcmd):
        from .config import ACE_INSTANCES
        printer = get_printer()
        eventtime = printer.get_reactor().monotonic()
        out, bad, warn = [], 0, 0

        def line(kind, text):
            nonlocal bad, warn
            if kind == "FAIL":
                bad += 1
            elif kind == "WARN":
                warn += 1
            out.append("%-5s %s" % (kind, text))

        if not ACE_INSTANCES:
            line("FAIL", "the ACE driver has no units configured")
        else:
            line("PASS", "driver loaded, %d unit(s) configured" % len(ACE_INSTANCES))
        for num in sorted(ACE_INSTANCES):
            try:
                st = ACE_INSTANCES[num].serial_mgr.get_connection_status()
            except Exception as exc:                   # keep the self-test going
                line("FAIL", "ACE[%d]: cannot read the connection (%s)" % (num, exc))
                continue
            if st.get("connected"):
                line("PASS", "ACE[%d] connected (%s)" % (num, st.get("port", "?")))
            else:
                line("FAIL", "ACE[%d] is not connected: check the USB cable and the power" % num)
        for num in sorted(ACE_INSTANCES):
            sensor = printer.lookup_object("temperature_sensor acepro_temp_%d" % (num + 1), None)
            if sensor is None:
                line("WARN", "no temperature sensor acepro_temp_%d" % (num + 1))
                continue
            temp = sensor.get_status(eventtime).get("temperature")
            if temp is None or temp <= 0:
                line("WARN", "ACE[%d] temperature reads %s" % (num, temp))
            else:
                line("PASS", "ACE[%d] temperature %.1f C" % (num, temp))
        # sensor names come from [ace] (filament_runout_sensor_name_nozzle / _rdm), as the driver uses them
        nozzle_name, rdm_name = "filament_runout_nozzle", None
        for inst in ACE_INSTANCES.values():
            nozzle_name = getattr(inst, "filament_runout_sensor_name_nozzle", None) or nozzle_name
            rdm_name = getattr(inst, "filament_runout_sensor_name_rdm", None) or rdm_name
            break
        nozzle = printer.lookup_object("filament_switch_sensor " + nozzle_name, None)
        if nozzle is None:
            line("FAIL", "no toolhead filament sensor (%s)" % nozzle_name)
        else:
            line("PASS", "toolhead sensor present (filament %s)" %
                 ("detected" if nozzle.get_status(eventtime).get("filament_detected") else "not detected"))
        for name in ((rdm_name,) if rdm_name else ("filament_runout_rdm",)):
            if printer.lookup_object("filament_switch_sensor " + name, None) is not None:
                line("PASS", "RDM sensor present")
        if printer.lookup_object("filament_motion_sensor ace_encoder", None) is not None:
            line("PASS", "encoder sensor present")
        macro = printer.lookup_object("gcode_macro _ACE_VARS", None)
        if macro is None:
            line("FAIL", "_ACE_VARS is missing: acepro_macros.cfg is not loaded")
        else:
            confirmed = str(getattr(macro, "variables", {}).get("positions_confirmed", "")).lower() == "true"
            if confirmed:
                line("PASS", "positions confirmed")
            else:
                line("WARN", "positions not confirmed: run ACE_SETUP_CUTTER / ACE_SETUP_BUCKET, then ACE_SETUP_CONFIRM")
        for pin in ("ACE_Pro", "AUTO_UNLOAD", "endless_spool", "bed_mesh_adaptive"):
            obj = printer.lookup_object("output_pin " + pin, None)
            if obj is not None:
                value = obj.get_status(eventtime).get("value")
                line("PASS", "switch %s is %s" % (pin, "ON" if value else "OFF"))
        out.append("Result: %d problem(s), %d warning(s). Nothing was changed." % (bad, warn))
        gcmd.respond_info("ACE self-test\n" + "\n".join(out))

    return [
        ("ACE_SETUP_SAVE", cmd_ACE_SETUP_SAVE,
         "Save the toolhead's current X/Y into acepro_macros.cfg. POINT=" + "|".join(sorted(POINTS))),
        ("ACE_SETUP_CONFIRM", cmd_ACE_SETUP_CONFIRM, "Mark the cutter / bucket positions as measured"),
        ("ACE_SELFTEST", cmd_ACE_SELFTEST, "Read-only health check of the ACE install. Nothing moves."),
    ]
