#!/usr/bin/env python3
"""Small config editor used by installer.sh. It only touches the files you name.

  ace_cfg_tool.py get      FILE SECTION KEY            print the value (exit 1 if missing)
  ace_cfg_tool.py set      FILE SECTION KEY VALUE      change a "key: value" line (keeps the trailing comment)
  ace_cfg_tool.py comment  FILE SECTION [NOTE]         comment out a section (up to the next blank line)
  ace_cfg_tool.py carry    OLD NEW                     copy your values from OLD into NEW (NEW is rewritten)
  ace_cfg_tool.py servo    OLD                         print the [servo servo_wipe] block found in OLD

"Option lines" are the unindented "key: value" or "key = value" lines. Indented lines (macro code,
multi-line values) are never read or changed by get/set/carry.
"""
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
    except OSError as exc:
        sys.stderr.write("%s\n" % exc)
        return 66
    sys.stderr.write(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv))
