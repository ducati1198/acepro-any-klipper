#!/usr/bin/env python3
"""Put the ACE Pro macros into their own Fluidd macro category (stored in Moonraker's database).

  fluidd_macros.py add    URL BACKUP_FILE NAME...   create the ACEPRO MACRO category and move NAME... into it
  fluidd_macros.py restore URL BACKUP_FILE          put a saved BACKUP_FILE back (used by --undo)
  fluidd_macros.py remove URL BACKUP_FILE           delete the category; its macros go back to Uncategorized

Only macros that are not in a category yet are moved, so macros you sorted yourself stay where you put them.
The old settings are written to BACKUP_FILE first. This is a display setting only; no printer file changes.
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

CATEGORY = "ACEPRO MACRO"
COLOR = "#ff00aa"


def _item(url):
    return url.rstrip("/") + "/server/database/item"


def load(url):
    try:
        with urllib.request.urlopen(_item(url) + "?namespace=fluidd&key=macros", timeout=5) as r:
            return json.load(r)["result"]["value"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def save(url, value):
    req = urllib.request.Request(
        _item(url), data=json.dumps({"namespace": "fluidd", "key": "macros", "value": value}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=5).read()


def backup(path, value):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=1)


def cmd_add(url, backup_file, names):
    cur = load(url)
    if cur is None:
        print("SKIP Fluidd has no saved macro settings on this printer")
        return 0
    backup(backup_file, cur)
    cats = cur.setdefault("categories", [])
    stored = cur.setdefault("stored", [])
    cat = next((c for c in cats if c.get("name", "").upper() == CATEGORY), None)
    if cat is None:
        cat = {"id": str(uuid.uuid4()), "name": CATEGORY}
        cats.append(cat)
    ids = {c["id"] for c in cats}
    by = {m["name"].lower(): m for m in stored}
    moved = 0
    for name in names:
        entry = by.get(name.lower())
        if entry is None:
            entry = {"alias": "", "visible": True, "disabledWhilePrinting": False,
                     "color": "", "categoryId": "", "name": name}
            stored.append(entry)
            by[name.lower()] = entry
        if entry.get("categoryId") in ids and entry.get("categoryId") != cat["id"]:
            continue                                   # you put it in another category: leave it
        if entry.get("categoryId") != cat["id"] or entry.get("color") != COLOR:
            entry["categoryId"], entry["color"] = cat["id"], COLOR
            moved += 1
    save(url, cur)
    print("OK %d macro(s) in category %s" % (moved, CATEGORY))
    return 0


def cmd_remove(url, backup_file):
    cur = load(url)
    if cur is None:
        return 0
    cat = next((c for c in cur.get("categories", []) if c.get("name", "").upper() == CATEGORY), None)
    if cat is None:
        print("SKIP no %s category" % CATEGORY)
        return 0
    backup(backup_file, cur)
    for m in cur.get("stored", []):
        if m.get("categoryId") == cat["id"]:
            m["categoryId"], m["color"] = "", ""
    cur["categories"] = [c for c in cur["categories"] if c["id"] != cat["id"]]
    save(url, cur)
    print("OK removed category %s" % CATEGORY)
    return 0


def cmd_restore(url, backup_file):
    with open(backup_file, encoding="utf-8") as fh:
        save(url, json.load(fh))
    print("OK Fluidd macro settings restored")
    return 0


def main(argv):
    try:
        if len(argv) >= 4 and argv[1] == "add":
            return cmd_add(argv[2], argv[3], argv[4:])
        if len(argv) == 4 and argv[1] == "restore":
            return cmd_restore(argv[2], argv[3])
        if len(argv) == 4 and argv[1] == "remove":
            return cmd_remove(argv[2], argv[3])
    except (OSError, ValueError, KeyError) as exc:
        sys.stderr.write("fluidd_macros: %s\n" % exc)
        return 2
    sys.stderr.write(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv))
