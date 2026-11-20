#!/usr/bin/env python3
"""Local preview server for the Plan2Stream project page.

Serves docs/ at / and the local encoded media/ directory at /media/, so the page
can be previewed before the videos are uploaded as GitHub Release assets.
main.js switches to /media/ automatically when the page is served from localhost.

Supports HTTP Range requests (206 Partial Content), which browsers need to seek in
long videos such as the hour-scale demos; GitHub Release downloads support them too.

Usage: python3 tools/serve.py [--port 8766]   (then forward the port in VS Code)
"""
import argparse
import functools
import http.server
import os
import re
from typing import BinaryIO, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


class Handler(http.server.SimpleHTTPRequestHandler):
    _range_left: Optional[int] = None

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/media/"):
            return os.path.join(ROOT, "media", clean[len("/media/"):])
        return os.path.join(ROOT, "docs", clean.lstrip("/"))

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self) -> Optional[BinaryIO]:
        self._range_left = None
        match = RANGE_RE.match(self.headers.get("Range", "").strip())
        path = self.translate_path(self.path)
        if not match or os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        size = os.fstat(f.fileno()).st_size
        first, last = match.groups()
        if first == "":  # suffix range: last N bytes
            start, end = max(0, size - int(last or 0)), size - 1
        else:
            start, end = int(first), min(int(last) if last else size - 1, size - 1)
        if start >= size or start > end:
            f.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        f.seek(start)
        self._range_left = end - start + 1
        return f

    def copyfile(self, source: BinaryIO, outputfile: BinaryIO) -> None:
        left = self._range_left
        if left is None:
            try:
                super().copyfile(source, outputfile)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        while left > 0:
            chunk = source.read(min(1 << 16, left))
            if not chunk:
                break
            try:
                outputfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):  # the browser cancelled this range
                break
            left -= len(chunk)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = http.server.ThreadingHTTPServer((args.host, args.port), functools.partial(Handler))
    print(f"Plan2Stream page: http://{args.host}:{args.port}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
