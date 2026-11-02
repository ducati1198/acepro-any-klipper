#!/usr/bin/env python3
"""Small config editor used by installer.sh. It only touches the files you name.

  ace_cfg_tool.py get      FILE SECTION KEY            print the value (exit 1 if missing)
  ace_cfg_tool.py set      FILE SECTION KEY VALUE      change a "key: value" line (keeps the trailing comment)
  ace_cfg_tool.py comment  FILE SECTION [NOTE]         comment out a section (up to the next blank line)
  ace_cfg_tool.py carry    OLD NEW                     copy your values from OLD into NEW (NEW is rewritten)
  ace_cfg_tool.py servo    OLD                         print the [servo servo_wipe] block found in OLD
  ace_cfg_tool.py hooks    TEMPLATE TARGET OUT ENCODER [SKIP]  put the ACE lines at the TOP of each Simple AF hook macro
                                                       (TARGET = your file or '-'; ENCODER 1|0; SKIP = macros defined elsewhere)
  ace_cfg_tool.py hooknames TEMPLATE                   list the hook macros of the template
  ace_cfg_tool.py hookcmds TEMPLATE NAME               list the ACE commands the template puts in one hook

"Option lines" are the unindented "key: value" or "key = value" lines. Indented lines (macro code,
multi-line values) are never read or changed by get/set/carry.
"""
import os
import re
import sys

HEADER = re.compile(r"^\[(.+?)\]\s*(?:[#;].*)?$")
OPTION = re.compile(r"^([A-Za-z_][^:=\s]*)(\s*[:=]\s*)(.*?)((?:\s+[#;].*)?)$")


def read(path):
    with open(path, encoding="utf-8", errors="surrogateescape") as fh:
        return fh.read().split("\n")


def write(path, lines):
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write("\n".join(lines))


def sections(lines):
    """Yield (section_name, option_dict{key: line_index}) for every section."""
    cur, opts = None, {}
    for i, line in enumerate(lines):
        h = HEADER.match(line) if line[:1] == "[" else None
        if h:
            if cur is not None:
                yield cur, opts
            cur, opts = h.group(1).strip(), {}
            continue
        if cur is not None and line[:1] not in (" ", "\t", "#", ";", ""):
            m = OPTION.match(line)
            if m:
                opts.setdefault(m.group(1), i)
    if cur is not None:
        yield cur, opts


def find(lines, section, key):
    for name, opts in sections(lines):
        if name == section and key in opts:
            return opts[key]
    return None


def cmd_get(f, section, key):
    lines = read(f)
    i = find(lines, section, key)
    if i is None:
        return 1
    print(OPTION.match(lines[i]).group(3))
    return 0


def cmd_set(f, section, key, value):
    lines = read(f)
    i = find(lines, section, key)
    if i is None:
        sys.stderr.write("not found: [%s] %s in %s\n" % (section, key, f))
        return 2
    m = OPTION.match(lines[i])
    comment = m.group(4)
    lines[i] = "%s%s%s%s" % (m.group(1), m.group(2), value, comment)
    write(f, lines)
    return 0


def cmd_comment(f, section, note=""):
    lines = read(f)
    start = None
    for i, line in enumerate(lines):
        h = HEADER.match(line) if line[:1] == "[" else None
        if h and h.group(1).strip() == section:
            start = i
            break
    if start is None:
        sys.stderr.write("section not found: [%s] in %s\n" % (section, f))
        return 2
    end = start
    while end < len(lines) and lines[end].strip() != "" and not (end > start and lines[end][:1] == "["):
        end += 1
    block = ["#" + l if l.strip() else l for l in lines[start:end]]
    prefix = ["# " + note] if note else []
    lines[start:end] = prefix + block
    write(f, lines)
    return 0


def cmd_carry(old, new):
    o, n = read(old), read(new)
    old_map = {}
    for name, opts in sections(o):
        old_map.setdefault(name, {}).update({k: o[i] for k, i in opts.items()})
    carried = 0
    for name, opts in list(sections(n)):
        for key, i in opts.items():
            line = old_map.get(name, {}).get(key)
            if line is not None and line != n[i]:
                n[i] = line
                carried += 1
    write(new, n)
    print(carried)
    return 0


def cmd_servo(old):
    lines = read(old)
    for i, line in enumerate(lines):
        if line.strip().startswith("[servo servo_wipe]") and line[:1] == "[":
            j = i
            while j < len(lines) and lines[j].strip() != "":
                j += 1
            print("\n".join(lines[i:j]))
            return 0
    return 1


ENCODER_CMDS = ("SFS_ENABLE_ACE_ENCODER", "SFS_DISABLE_ACE_ENCODER")


def _first_word(line):
    t = line.strip()
    if not t or t[0] in "#;" or t.startswith("{"):
        return ""
    return re.split(r"[\s#;]", t, maxsplit=1)[0]


def parse_hook_template(lines):
    """Return (header_lines, [(name, [item, ...])]). An item is {key, lines, encoder}."""
    header, macros, cur = [], [], None
    for line in lines:
        h = HEADER.match(line) if line[:1] == "[" else None
        if h:
            m = re.match(r"gcode_macro\s+(\S+)$", h.group(1).strip())
            cur = (m.group(1), []) if m else None
            if cur:
                macros.append(cur)
            continue
        if cur is None:
            header.append(line)
            continue
        if not line.strip() or line.strip() == "gcode:":
            continue
        cur[1].append(line)
    out = []
    for name, body in macros:
        items, blk = [], None
        for line in body:
            txt = line.strip()
            enc = "#ENCODER" in txt
            if enc:
                txt = txt.replace("#ENCODER ", "# ").replace("#ENCODER", "").rstrip()
            if blk is not None:
                blk["lines"].append(line.rstrip())
                if not blk["key"] and _first_word(line):
                    blk["key"] = _first_word(line)
                if "{% endif %}" in txt:
                    items.append(blk)
                    blk = None
                continue
            if txt.startswith("{%"):
                blk = {"key": "", "lines": [line.rstrip()], "encoder": False}
                continue
            items.append({"key": _first_word(txt), "lines": [txt], "encoder": enc})
        out.append((name, items))
    return header, out


def _indent_of(body):
    for line in body:
        if line.strip() and line.strip()[0] not in "#;" and line[:1] in " \t":
            return line[: len(line) - len(line.lstrip())]
    return "    "


def _render(item, indent):
    ls = item["lines"]
    if len(ls) == 1:
        return [indent + ls[0].strip()]
    base = len(ls[0]) - len(ls[0].lstrip())
    return [indent + l[base:] if l.strip() else l for l in ls]


def cmd_hooks(template, target, out, encoder, skip=""):
    """Write the Simple AF hooks file: ACE lines go to the TOP of each hook macro.

    TARGET is your existing file ('-' if there is none). Everything in it that is not an ACE line is
    kept as it is; macros it lacks are added at the end. ENCODER is 1 or 0: with 0 the
    SFS_ENABLE/DISABLE_ACE_ENCODER lines are removed. SKIP is a comma list of macros that are
    defined in another file (they are not touched here).
    """
    keep_encoder = encoder == "1"
    skipped = set(x for x in skip.split(",") if x)
    header, macros = parse_hook_template(read(template))
    exists = target != "-" and os.path.exists(target)
    lines = read(target) if exists else []
    if not exists:
        while header and not header[-1].strip():
            header.pop()
        lines = [l for l in header] + [""]
    report = []

    def want(item):
        return keep_encoder or not item["encoder"]

    # index macros in the target
    def find_macro(name):
        start = None
        for i, line in enumerate(lines):
            h = HEADER.match(line) if line[:1] == "[" else None
            if h and h.group(1).split() == ["gcode_macro", name]:
                start = i
                break
        if start is None:
            return None
        end = start + 1
        while end < len(lines) and not (lines[end][:1] == "[" and HEADER.match(lines[end])):
            end += 1
        return start, end

    for name, items in macros:
        if name in skipped:
            report.append("SKIPPED %s (defined in another file)" % name)
            continue
        found = find_macro(name)
        if found is None:
            use = [i for i in items if want(i)]
            if not any(i["key"] for i in use):
                continue
            if lines and lines[-1].strip():
                lines.append("")
            lines.append("[gcode_macro %s]" % name)
            lines.append("gcode:")
            for i in use:
                lines.extend(_render(i, "    "))
            lines.append("")
            report.append("ADDED %s" % name)
            continue
        start, end = found
        gi = None
        for k in range(start + 1, end):
            if re.match(r"^gcode\s*:\s*(?:[#;].*)?$", lines[k]):
                gi = k
                break
        if gi is None:
            report.append("SKIPPED %s (its gcode: line is not on its own)" % name)
            continue
        body = lines[gi + 1:end]
        indent = _indent_of(body)
        moved, added, removed = [], [], []
        # encoder lines: always the first lines of the macro
        top = []
        for item in items:
            if not item["encoder"]:
                continue
            cmd = item["key"]
            existing = [l for l in body if _first_word(l) == cmd]
            body = [l for l in body if _first_word(l) != cmd]
            if keep_encoder:
                top.append(existing[0] if existing else indent + item["lines"][0].strip())
                (moved if existing else added).append(cmd)
            elif existing:
                removed.append(cmd)
        # encoder lines of the other direction that the template does not list for this macro
        if not keep_encoder:
            for l in list(body):
                if _first_word(l) in ENCODER_CMDS:
                    body.remove(l)
                    removed.append(_first_word(l))
        # the other ACE lines, only when missing
        for item in items:
            if item["encoder"] or not item["key"]:
                continue
            present = any(_first_word(l) == item["key"] for l in body)
            if not present:
                top.extend(_render(item, indent))
                added.append(item["key"])
        before = lines[gi + 1:end]
        if top + body == before:
            continue                         # already as wanted: leave the file as it is
        lines[gi + 1:end] = top + body
        bits = []
        if added:
            bits.append("added " + ", ".join(added))
        if moved:
            bits.append("moved to top " + ", ".join(moved))
        if removed:
            bits.append("removed " + ", ".join(removed))
        if bits:
            report.append("UPDATED %s: %s" % (name, "; ".join(bits)))
    if not exists:
        text = "\n".join(lines).rstrip("\n") + "\n"
    else:
        text = "\n".join(lines)
    with open(out, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(text)
    for r in report:
        print(r)
    return 0


def cmd_hooknames(template):
    for name, items in parse_hook_template(read(template))[1]:
        print(name)
    return 0


def cmd_hookcmds(template, name):
    for n, items in parse_hook_template(read(template))[1]:
        if n == name:
            print(", ".join(i["key"] for i in items if i["key"]))
    return 0


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 64
    c, a = argv[1], argv[2:]
    try:
        if c == "get" and len(a) == 3:
            return cmd_get(*a)
        if c == "set" and len(a) == 4:
            return cmd_set(*a)
        if c == "comment" and len(a) in (2, 3):
            return cmd_comment(*a)
        if c == "carry" and len(a) == 2:
            return cmd_carry(*a)
        if c == "servo" and len(a) == 1:
            return cmd_servo(*a)
        if c == "hooks" and len(a) in (4, 5):
            return cmd_hooks(*a)
        if c == "hooknames" and len(a) == 1:
            return cmd_hooknames(*a)
        if c == "hookcmds" and len(a) == 2:
            return cmd_hookcmds(*a)
    except OSError as exc:
        sys.stderr.write("%s\n" % exc)
        return 66
    sys.stderr.write(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv))
