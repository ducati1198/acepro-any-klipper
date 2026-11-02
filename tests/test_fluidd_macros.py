import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import fluidd_macros as fm  # noqa: E402


def serve(db):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if db["value"] is None:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"result": {"value": db["value"]}}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            db["value"] = json.loads(self.rfile.read(n))["value"]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_port


def base():
    return {"categories": [{"id": "c1", "name": "FILAMENT"}],
            "stored": [{"alias": "", "visible": True, "disabledWhilePrinting": False, "color": "#ff7c00",
                        "categoryId": "c1", "name": "LOAD_FILAMENT"}], "expanded": []}


def test_add_creates_category_and_keeps_user_choices(tmp_path):
    db = {"value": base()}
    srv, url = serve(db)
    try:
        fm.cmd_add(url, str(tmp_path / "bk.json"), ["CUT_TIP", "LOAD_FILAMENT", "SERVO_TEST"])
    finally:
        srv.shutdown()
    v = db["value"]
    cat = [c for c in v["categories"] if c["name"] == "ACEPRO MACRO"]
    assert len(cat) == 1
    by = {m["name"]: m for m in v["stored"]}
    assert by["CUT_TIP"]["categoryId"] == cat[0]["id"] and by["CUT_TIP"]["color"] == "#ff00aa"
    assert by["SERVO_TEST"]["categoryId"] == cat[0]["id"]
    assert by["LOAD_FILAMENT"]["categoryId"] == "c1" and by["LOAD_FILAMENT"]["color"] == "#ff7c00"
    assert json.load(open(tmp_path / "bk.json")) == base()


def test_add_twice_is_idempotent(tmp_path):
    db = {"value": base()}
    srv, url = serve(db)
    try:
        fm.cmd_add(url, str(tmp_path / "b"), ["CUT_TIP"])
        fm.cmd_add(url, str(tmp_path / "b"), ["CUT_TIP", "TR"])
    finally:
        srv.shutdown()
    assert len([c for c in db["value"]["categories"] if c["name"] == "ACEPRO MACRO"]) == 1
    assert len([m for m in db["value"]["stored"] if m["name"] == "CUT_TIP"]) == 1
    assert any(m["name"] == "TR" for m in db["value"]["stored"])


def test_remove_restores_uncategorized(tmp_path):
    db = {"value": base()}
    srv, url = serve(db)
    try:
        fm.cmd_add(url, str(tmp_path / "b"), ["CUT_TIP"])
        fm.cmd_remove(url, str(tmp_path / "b2"))
    finally:
        srv.shutdown()
    assert [c["name"] for c in db["value"]["categories"]] == ["FILAMENT"]
    cut = [m for m in db["value"]["stored"] if m["name"] == "CUT_TIP"][0]
    assert cut["categoryId"] == "" and cut["color"] == ""


def test_no_fluidd_settings_is_skipped(tmp_path, capsys):
    db = {"value": None}
    srv, url = serve(db)
    try:
        assert fm.cmd_add(url, str(tmp_path / "b"), ["CUT_TIP"]) == 0
    finally:
        srv.shutdown()
    assert "SKIP" in capsys.readouterr().out and db["value"] is None
