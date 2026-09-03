"""Static assets: content-hashed fonts, one stylesheet, one script."""

import hashlib
import shutil
from pathlib import Path

# Vazirmatn FD renders Latin digits as Persian glyphs; the plain face is used for
# .en / code so "ISO 26000" keeps Latin digits.
FACES = [
    ('Vazirmatn-FD-Regular.woff2', 'Vazirmatn FD', 400),
    ('Vazirmatn-FD-Medium.woff2', 'Vazirmatn FD', 500),
    ('Vazirmatn-FD-Bold.woff2', 'Vazirmatn FD', 700),
    ('Vazirmatn-Regular.woff2', 'Vazirmatn', 400),
    ('Vazirmatn-Bold.woff2', 'Vazirmatn', 700),
]


def hash8(data):
    return hashlib.sha256(data).hexdigest()[:8]


def _emit(data, out_dir, name, suffix):
    out = out_dir / f'{name}.{hash8(data)}{suffix}'
    out.write_bytes(data)
    return f'/static/{out_dir.name}/{out.name}'


def copy_static(root, dist):
    """Everything in static/ except fonts/, which are emitted with hashed names."""
    shutil.copytree(root / 'static', dist / 'static',
                    ignore=shutil.ignore_patterns('fonts'))


def emit_css(root, dist, extra=''):
    fonts_out = dist / 'static' / 'fonts'
    css_out = dist / 'static' / 'css'
    fonts_out.mkdir(parents=True, exist_ok=True)
    css_out.mkdir(parents=True, exist_ok=True)

    faces, preload = [], None
    for filename, family, weight in FACES:
        data = (root / 'static' / 'fonts' / filename).read_bytes()
        url = _emit(data, fonts_out, filename[:-len('.woff2')], '.woff2')
        if family == 'Vazirmatn FD' and weight == 400:
            preload = url
        faces.append(
            f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};'
            f'font-display:swap;src:url({url}) format("woff2")}}'
        )

    main = (root / 'src' / 'css' / 'main.css').read_text(encoding='utf-8')
    # `extra` carries build-generated rules (chapter hues). They belong in the
    # stylesheet because the CSP forbids inline style attributes.
    bundle = '\n'.join(faces) + '\n' + main + '\n' + extra
    url = _emit(bundle.encode('utf-8'), css_out, 'site', '.css')
    return {'cssUrl': url, 'preloadFont': preload}


def emit_js(root, dist):
    js = (root / 'src' / 'js' / 'app.js').read_bytes()
    out = dist / 'static' / 'js'
    out.mkdir(parents=True, exist_ok=True)
    return _emit(js, out, 'app', '.js')
