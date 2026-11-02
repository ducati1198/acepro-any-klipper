"""Tiny stand-in for Moonraker's database API, for the installer tests.
usage: fake_moonraker.py DB_JSON_FILE PORT_FILE   (serves until killed; the value lives in DB_JSON_FILE)"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

db_file, port_file = sys.argv[1], sys.argv[2]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        with open(db_file) as fh:
            value = json.load(fh)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"result": {"value": value}}).encode())

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        value = json.loads(self.rfile.read(n))["value"]
        with open(db_file, "w") as fh:
            json.dump(value, fh)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")


srv = HTTPServer(("127.0.0.1", 0), H)
with open(port_file, "w") as fh:
    fh.write(str(srv.server_port))
srv.serve_forever()
