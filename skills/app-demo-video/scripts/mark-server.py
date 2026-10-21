#!/usr/bin/env python3
"""Records named moments sent by the Maestro flows (flows/lib/mark.js).

Usage: mark-server.py <marks-file> [port]
Each POST /mark with a body of NAME appends "NAME <unix-time>" to the file.
make-video.sh also appends the moment each simulator recording started, so
every mark can be turned into an offset into either recording.
"""
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

marks_file = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8787


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        name = self.rfile.read(length).decode().strip() or "unnamed"
        with open(marks_file, "a") as f:
            f.write(f"{name} {time.time():.3f}\n")
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
