#!/usr/bin/env python3
"""Build the site, then serve it. The container's entrypoint.

Runs one build at startup and then watches the sources, so a `git pull` on
the host is picked up within a couple of seconds without restarting the
container. Replaces nginx: caching, compression and the security headers
that used to live in nginx.conf are all here.

    python3 build/serve.py [--port 9237] [--no-watch]
"""

import argparse
import gzip
import hashlib
import mimetypes
import os
import subprocess
import sys
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# MBA_DIST lets the container build into a writable dir while /app stays read-only.
DIST = Path(os.environ.get('MBA_DIST') or ROOT / 'dist')
BUILD = ROOT / 'build' / 'build.py'
WATCH = [ROOT / 'src', ROOT / 'static', ROOT / 'build']

# The inline theme script in layout.py is allowlisted by hash; update both together.
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
       "script-src 'self' 'sha256-nvfcR/rTu7RYxJt8oq5oqFAp1n1DZUJ8WpumS8otJe4='; "
       "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

COMPRESSIBLE = {
    'text/html', 'text/css', 'text/plain', 'text/xml',
    'application/javascript', 'application/json', 'application/xml',
    'image/svg+xml',
}
CHARSET = {'text/html', 'text/css', 'text/plain', 'text/xml',
           'application/javascript', 'application/json', 'application/xml'}
MIN_GZIP = 512

mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('font/woff2', '.woff2')


def cache_control(url_path):
    # Content-hashed filenames, so these can never go stale.
    if url_path.startswith('/static/'):
        return 'public, max-age=31536000, immutable'
    if url_path == '/search-index.json':
        return 'public, max-age=3600'
    if url_path in ('/sitemap.xml', '/robots.txt'):
        return 'public, max-age=86400'
    return 'no-cache'


class Handler(SimpleHTTPRequestHandler):
    server_version = 'mbatalks'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stdout.write('%s %s\n' % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()

    def do_GET(self):
        self._respond(body=True)

    def do_HEAD(self):
        self._respond(body=False)

    def _resolve(self):
        """URL -> (file, url_path) following nginx's try_files $uri $uri/ $uri/index.html."""
        url_path = self.path.split('?', 1)[0].split('#', 1)[0]
        local = Path(self.translate_path(self.path))
        if local.is_dir():
            if not url_path.endswith('/'):
                return 'redirect', url_path + '/'
            local = local / 'index.html'
        if local.is_file():
            return local, url_path
        return None, url_path

    def _respond(self, body):
        target, url_path = self._resolve()

        if target == 'redirect':
            # Kept relative so the published URL never leaks the container's port.
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header('Location', url_path)
            self.send_header('Content-Length', '0')
            self._common_headers()
            self.end_headers()
            return

        status = HTTPStatus.OK
        if target is None:
            target = DIST / '404.html'
            status = HTTPStatus.NOT_FOUND
            if not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, 'Not Found')
                return

        try:
            data = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, 'Not Found')
            return

        ctype = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        etag = '"%s"' % hashlib.sha256(data).hexdigest()[:16]

        if status == HTTPStatus.OK and self.headers.get('If-None-Match') == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', cache_control(url_path))
            self._common_headers()
            self.end_headers()
            return

        encoding = None
        if (ctype in COMPRESSIBLE and len(data) >= MIN_GZIP
                and 'gzip' in self.headers.get('Accept-Encoding', '')):
            data = gzip.compress(data, 6)
            encoding = 'gzip'

        self.send_response(status)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype in CHARSET else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', cache_control(url_path))
        self.send_header('ETag', etag)
        if ctype in COMPRESSIBLE:
            self.send_header('Vary', 'Accept-Encoding')
        if encoding:
            self.send_header('Content-Encoding', encoding)
        self._common_headers()
        self.end_headers()
        if body:
            self.wfile.write(data)

    def _common_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy', CSP)


def build():
    r = subprocess.run([sys.executable, str(BUILD)], cwd=str(ROOT))
    if r.returncode != 0:
        print('✗ build failed — serving the previous dist/', file=sys.stderr, flush=True)
    return r.returncode == 0


def fingerprint():
    stamp = 0.0
    for base in WATCH:
        for path in base.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                stamp = max(stamp, path.stat().st_mtime)
    return stamp


def watch(interval=2.0):
    """Rebuild when the sources change, so `git pull` needs no restart."""
    last = fingerprint()
    while True:
        time.sleep(interval)
        try:
            now = fingerprint()
        except OSError:
            continue
        if now != last:
            last = now
            print('· sources changed, rebuilding', flush=True)
            build()
            last = fingerprint()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 9237)))
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--no-watch', action='store_true')
    args = ap.parse_args()

    if not build() and not DIST.is_dir():
        return 1

    if not args.no_watch:
        threading.Thread(target=watch, daemon=True).start()

    httpd = ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(DIST)))
    httpd.daemon_threads = True
    print(f'→ serving {DIST} on http://{args.host}:{args.port}', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
