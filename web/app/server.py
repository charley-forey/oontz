"""Static server for the oontz landing terminal.

Vercel is the intended host, but this keeps the site deployable anywhere that can
run Python, which is what got it live the day the Vercel free tier ran out of
deployments. No dependencies.
"""
import os
import http.server
import socketserver

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8080"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "public, max-age=60")
        super().end_headers()

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if self.path == "/" or ("." not in os.path.basename(self.path) and not self.path.endswith("/")):
            self.path = "/index.html"          # single page, any route
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass                                    # Railway captures stdout; keep it quiet


socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print("landing on :%d" % PORT, flush=True)
    httpd.serve_forever()
