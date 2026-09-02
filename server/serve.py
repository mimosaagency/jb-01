#!/usr/bin/env python3
"""JUKEBOX local server: no-cache static files + a save endpoint for recordings."""
import http.server, socketserver, functools, os, re, datetime, subprocess
from urllib.parse import unquote

DIR  = os.environ.get("JB01_DIR") or os.path.dirname(os.path.abspath(__file__))
# defaults to this folder; point JB01_DIR at wherever index.html lives
RECS = os.path.join(DIR, "recordings")
PORT = 8080
os.makedirs(RECS, exist_ok=True)

SAFE = re.compile(r'^[A-Za-z0-9._-]{1,80}$')

class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        # /reveal?name=<file>  -> open the recording in the Finder.
        # Name is matched against SAFE and basenamed, so it cannot escape RECS.
        if self.path.startswith("/reveal"):
            name = ""
            if "?" in self.path:
                for kv in self.path.split("?",1)[1].split("&"):
                    if kv.startswith("name="):
                        name = unquote(kv[5:])
            name = os.path.basename(name)
            dest = os.path.join(RECS, name)
            if not name or not SAFE.match(name) or not os.path.isfile(dest):
                self.send_error(404); return
            subprocess.run(["/usr/bin/open", "-R", dest], check=False)
            self.send_response(204); self.end_headers(); return
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/log"):
            try: n=int(self.headers.get("Content-Length",0))
            except ValueError: n=0
            body=self.rfile.read(min(n,8192)).decode("utf-8","replace")
            with open(os.path.join(DIR,"client.log"),"a") as f:
                f.write("%s  %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), body))
            self.send_response(204); self.end_headers(); return
        if not self.path.startswith("/save"):
            self.send_error(404); return
        name = ""
        if "?" in self.path:
            for kv in self.path.split("?",1)[1].split("&"):
                if kv.startswith("name="):
                    name = kv[5:]
        if not name or not SAFE.match(name) or not name.endswith(".wav"):
            name = "jukebox-%s.wav" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n <= 0 or n > 600*1024*1024:
            self.send_error(400, "bad length"); return
        dest = os.path.join(RECS, os.path.basename(name))
        left = n
        with open(dest, "wb") as f:
            while left > 0:
                buf = self.rfile.read(min(1024*1024, left))
                if not buf: break
                f.write(buf); left -= len(buf)
        body = ("saved %s (%.1f MB)" % (os.path.basename(dest), n/1048576)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    handler = functools.partial(H, directory=DIR)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()
