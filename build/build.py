#!/usr/bin/env python3
"""Static site generator. Python standard library only — no package manager.

    python3 build/build.py
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))

import assets as assets_mod  # noqa: E402
import tex  # noqa: E402
from layout import render_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# MBA_DIST lets the container build into a writable dir while /app stays read-only.
DIST = Path(os.environ.get('MBA_DIST') or ROOT / 'dist')
CONTENT = ROOT / 'src' / 'content'
QUESTIONS = ROOT / 'src' / 'questions.json'

META_RE = re.compile(r'^\s*<!--meta\s*(.*?)-->', re.S)
VOCAB_RE = re.compile(
    r'<li><span class="fa">(.*?)</span><span class="en">(.*?)</span></li>', re.S)
DISPLAY_RE = re.compile(r'<div class="math">(.*?)</div>', re.S)
INLINE_RE = re.compile(r'<span class="math-inline">(.*?)</span>', re.S)
TAG_RE = re.compile(r'<[^>]+>')
# Formulas are typeset from Latin metrics only; Persian belongs in the caption.
ARABIC_RE = re.compile(r'[؀-ۿ]')

warnings = []


class BuildError(Exception):
    pass


def unescape_tex(s):
    return (s.replace('&lt;', '<').replace('&gt;', '>')
             .replace('&quot;', '"').replace('&amp;', '&'))


def parse_fragment(raw, name):
    m = META_RE.match(raw)
    if not m:
        raise BuildError(f'{name}: missing <!--meta ... --> block')
    try:
        meta = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise BuildError(f'{name}: meta is not valid JSON — {e}') from None
    return meta, raw[m.end():].strip()


def render_math(html, name):
    def one(src, display):
        source = unescape_tex(src).strip()
        if ARABIC_RE.search(source):
            warnings.append(
                f'{name}: Persian text inside a formula — move it to the caption: "{source[:40]}…"')
        try:
            return tex.render(source, display)
        except ValueError as e:
            raise BuildError(f'{name}: formula "{source[:60]}" — {e}') from None

    html = DISPLAY_RE.sub(lambda m: one(m.group(1), True), html)
    return INLINE_RE.sub(lambda m: one(m.group(1), False), html)


def word_count(html):
    return len(TAG_RE.sub(' ', html).split())


def check_meta(meta, name, need_description=True):
    if not meta.get('title'):
        raise BuildError(f'{name}: meta.title is required')
    if need_description:
        if not meta.get('description'):
            raise BuildError(f'{name}: meta.description is required')
        n = len(meta['description'])
        if n < 80 or n > 180:
            warnings.append(f'{name}: description is {n} chars (aim for 120–170)')


def load_content(site):
    chapters = []
    for d in sorted(p for p in CONTENT.iterdir()
                    if p.is_dir() and re.match(r'^\d+-', p.name)):
        slug = re.sub(r'^\d+-', '', d.name)
        meta, body = parse_fragment(
            (d / '_chapter.html').read_text(encoding='utf-8'), f'{d.name}/_chapter.html')
        check_meta(meta, f'{d.name}/_chapter.html')

        topics = []
        for f in sorted(p for p in d.glob('*.html') if not p.name.startswith('_')):
            name = f'{d.name}/{f.name}'
            tmeta, tbody = parse_fragment(f.read_text(encoding='utf-8'), name)
            check_meta(tmeta, name)
            tslug = tmeta.get('slug') or re.sub(r'^\d+-', '', f.stem)
            topics.append({**tmeta, 'slug': tslug, 'url': f'/{slug}/{tslug}/',
                           'body': tbody, 'words': word_count(tbody), 'file': name})

        weight = meta.get('weight')
        chapters.append({**meta, 'slug': slug, 'url': f'/{slug}/', 'body': body,
                         'topics': topics,
                         'weightLabel': meta.get('weightLabel') or (str(weight) if weight else '')})

    order = site['chapterOrder']
    chapters.sort(key=lambda c: order.index(c['slug']))
    for i, c in enumerate(chapters):
        c['hue'] = round(i * 360 / len(chapters))
    return chapters


def order_index(slug, site):
    return site['chapterOrder'].index(slug)


def load_guides():
    """Standalone pages under _pages/ — reference material that sits outside the
    book's chapter sequence (exam guide, glossary, FAQ, question bank)."""
    d = CONTENT / '_pages'
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob('*.html')):
        name = f'_pages/{f.name}'
        meta, body = parse_fragment(f.read_text(encoding='utf-8'), name)
        check_meta(meta, name)
        slug = meta.get('slug') or re.sub(r'^\d+-', '', f.stem)
        out.append({**meta, 'slug': slug, 'url': f'/{slug}/', 'body': body,
                    'words': word_count(body), 'file': name})
    return out


def glossary_html(chapters):
    """Derive the glossary from the vocabulary lists already on the topic pages,
    so it cannot drift out of sync with them."""
    terms = {}
    for ch in chapters:
        for t in ch['topics']:
            for fa, en in VOCAB_RE.findall(t['body']):
                terms.setdefault(fa.strip(), {'en': en.strip(), 'seen': []})
                terms[fa.strip()]['seen'].append(t)

    # Persian collation: fold the alef variants so آ/ا/أ sort together.
    def key(s):
        return re.sub(r'[آأإ]', 'ا', s).replace('\u200c', ' ')

    rows = ''.join(
        f'<tr><td>{fa}</td><td><span class="en">{v["en"]}</span></td>'
        + '<td>' + '، '.join(
            f'<a href="{t["url"]}">{t["title"]}</a>' for t in v['seen']) + '</td></tr>'
        for fa, v in sorted(terms.items(), key=lambda kv: key(kv[0])))
    return (f'<p class="glossary-count">{len(terms)} اصطلاح</p>'
            '<div class="table-wrap"><table><thead><tr>'
            '<th>اصطلاح</th><th>معادل انگلیسی</th><th>در این مبحث</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>')


LETTERS = ('الف', 'ب', 'پ', 'ت')


def render_questions(items, by_url, offset=0):
    """Render a numbered question list. Each question carries a worked
    explanation and a link back to the topic that covers it."""
    out = []
    for i, q in enumerate(items, start=offset + 1):
        opts = ''.join(
            f'<li><span class="opt-key">{LETTERS[j]}</span>{o}</li>'
            for j, o in enumerate(q['options']))
        topic = by_url.get('/' + q['topic'].strip('/') + '/')
        link = (f'<a class="q-topic" href="{topic["url"]}">مطالعه مبحث: {topic["title"]}</a>'
                if topic else '')
        if not topic:
            warnings.append(f'questions.json: topic "{q["topic"]}" does not resolve')
        wrong = f'<p class="q-wrong"><b>چرا بقیه نه:</b> {q["wrong"]}</p>' if q.get('wrong') else ''
        out.append(
            f'<li class="q" id="q{i}"><p class="q-text">{q["q"]}</p>'
            f'<ol class="q-options">{opts}</ol>'
            f'<details class="q-answer"><summary>پاسخ و توضیح</summary>'
            f'<p class="q-correct">گزینه <b>{LETTERS[q["answer"]]}</b></p>'
            f'<p>{q["why"]}</p>{wrong}{link}</details></li>')
    return f'<ol class="q-list">{"".join(out)}</ol>'


def write_page(url, html):
    d = DIST / url.strip('/')
    d.mkdir(parents=True, exist_ok=True)
    (d / 'index.html').write_text(html, encoding='utf-8')


def main():
    site = json.loads((ROOT / 'src' / 'site.json').read_text(encoding='utf-8'))
    # Empty the output directory rather than removing it: it may be a mount point.
    DIST.mkdir(parents=True, exist_ok=True)
    for child in DIST.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()

    assets_mod.copy_static(ROOT, DIST)
    asset_urls = assets_mod.emit_css(ROOT, DIST)
    asset_urls['jsUrl'] = assets_mod.emit_js(ROOT, DIST)

    chapters = load_content(site)

    # Flat reading order across the whole book, for prev/next.
    flat = []
    for ch in chapters:
        flat.append({'url': ch['url'], 'title': ch['title'], 'kind': 'chapter',
                     'chapter': ch, 'ref': ch})
        for t in ch['topics']:
            flat.append({'url': t['url'], 'title': t['title'], 'kind': 'topic',
                         'chapter': ch, 'ref': t})
    guides = load_guides()
    by_url = {e['url']: e for e in flat}
    by_url.update({g['url']: {'url': g['url'], 'title': g['title']} for g in guides})

    def resolve_related(items, source):
        out = []
        for r in items or []:
            url = '/' + r.strip('/') + '/'
            hit = by_url.get(url)
            if not hit:
                warnings.append(f'{source}: related link "{r}" does not resolve')
                continue
            out.append({'url': url, 'title': hit['title']})
        return out

    pages, search_index = [], []
    for i, entry in enumerate(flat):
        ref, chapter, kind = entry['ref'], entry['chapter'], entry['kind']
        source = ref.get('file') or f'{chapter["slug"]}/_chapter.html'
        page = {
            'kind': kind,
            'url': entry['url'],
            'title': ref['title'],
            'description': ref['description'],
            'keywords': ref.get('keywords'),
            'chapter': chapter,
            'html': render_math(ref['body'], source),
            'prev': flat[i - 1] if i > 0 else None,
            'next': flat[i + 1] if i < len(flat) - 1 else None,
            'related': resolve_related(ref.get('related'), source),
        }
        if kind == 'chapter':
            cards = ''.join(
                f'<li data-topic="{t["url"]}"><a href="{t["url"]}">'
                f'<b>{t["title"]}</b><span>{t["description"]}</span></a></li>'
                for t in chapter['topics'])
            page['html'] += f'<section class="topic-cards"><h2>مباحث این فصل</h2><ul>{cards}</ul></section>'
        pages.append(page)
        search_index.append({
            'u': entry['url'], 't': ref['title'], 'd': ref['description'],
            'k': ' '.join(ref.get('keywords') or []),
            'c': '' if kind == 'chapter' else chapter['title'],
        })

    for g in guides:
        pages.append({
            'kind': 'guide', 'url': g['url'], 'title': g['title'],
            'description': g['description'], 'keywords': g.get('keywords'),
            'chapter': None,
            'html': render_math(g['body'], g['file']).replace(
                '<!--GLOSSARY-->', glossary_html(chapters)),
            'prev': None, 'next': None,
            'related': resolve_related(g.get('related'), g['file']),
        })
        search_index.append({
            'u': g['url'], 't': g['title'], 'd': g['description'],
            'k': ' '.join(g.get('keywords') or []), 'c': 'راهنما',
        })

    if QUESTIONS.exists():
        bank = json.loads(QUESTIONS.read_text(encoding='utf-8'))
        by_slug = {c['slug']: c for c in chapters}
        made = []
        for slug, items in bank.items():
            ch = by_slug.get(slug)
            if not ch:
                warnings.append(f'questions.json: unknown chapter "{slug}"')
                continue
            url = f'/questions/{slug}/'
            title = f'سؤالات {ch["title"]}'
            desc = (f'نمونه سؤالات چهارگزینه‌ای {ch["title"]} آزمون مشاوران کسب و کار '
                    f'با پاسخ تشریحی و پیوند به مبحث مربوطه.')
            pages.append({
                'kind': 'guide', 'url': url, 'title': title, 'description': desc,
                'keywords': [f'سوالات {ch["title"]}', 'نمونه سوال آزمون مشاوران کسب و کار'],
                'chapter': None,
                'html': (f'<p class="lead">{len(items)} سؤال چهارگزینه‌ای از سرفصل '
                         f'<a href="{ch["url"]}">{ch["title"]}</a>. پاسخ هر سؤال همراه با '
                         'توضیح گزینه درست و دلیل نادرستی سایر گزینه‌ها آمده است.</p>'
                         + render_questions(items, by_url)),
                'prev': None, 'next': None,
                'related': [{'url': ch['url'], 'title': ch['title']}],
            })
            search_index.append({'u': url, 't': title, 'd': desc,
                                 'k': 'نمونه سوال آزمون', 'c': 'سؤالات'})
            made.append((slug, ch, len(items)))

        # Full mock paper: every question in exam order.
        allq, blocks, offset = [], [], 0
        for slug, ch, _ in sorted(made, key=lambda m: order_index(m[0], site)):
            items = bank[slug]
            blocks.append(f'<h2>{ch["title"]}</h2>' + render_questions(items, by_url, offset))
            offset += len(items)
            allq += items
        if allq:
            rows = ''.join(
                f'<tr><td><a href="/questions/{s}/">{c["title"]}</a></td>'
                f'<td>{n}</td></tr>' for s, c, n in
                sorted(made, key=lambda m: order_index(m[0], site)))
            hub_desc = (f'بانک {len(allq)} سؤال چهارگزینه‌ای آزمون صلاحیت حرفه‌ای مشاوران '
                        'کسب و کار ۱۴۰۵ با پاسخ تشریحی، به تفکیک سرفصل.')
            pages.append({
                'kind': 'guide', 'url': '/questions/', 'title': 'بانک سؤالات آزمون',
                'description': hub_desc,
                'keywords': ['سوالات آزمون صلاحیت حرفه ای مشاوران کسب و کار',
                             'نمونه سوال آزمون مشاوران کسب و کار', 'بانک سوالات'],
                'chapter': None,
                'html': (f'<p class="lead">{len(allq)} سؤال چهارگزینه‌ای با پاسخ تشریحی، '
                         'به تفکیک سرفصل و متناسب با وزن هر سرفصل در آزمون.</p>'
                         '<div class="table-wrap"><table><thead><tr><th>سرفصل</th>'
                         f'<th>تعداد سؤال</th></tr></thead><tbody>{rows}'
                         f'<tr><td><b>جمع</b></td><td><b>{len(allq)}</b></td></tr>'
                         '</tbody></table></div>'
                         '<p><a href="/questions/mock/">آزمون جامع — همه سؤالات یک‌جا</a></p>'),
                'prev': None, 'next': None, 'related': [],
            })
            search_index.append({'u': '/questions/', 't': 'بانک سؤالات آزمون', 'd': hub_desc,
                                 'k': 'نمونه سوال آزمون مشاوران کسب و کار', 'c': 'سؤالات'})
            mock_desc = (f'آزمون جامع {len(allq)} سؤالی مشاوران کسب و کار ۱۴۰۵ با پاسخ '
                         'تشریحی؛ همه سؤالات به ترتیب سرفصل در یک صفحه.')
            pages.append({
                'kind': 'guide', 'url': '/questions/mock/',
                'title': f'آزمون جامع {len(allq)} سؤالی',
                'description': mock_desc,
                'keywords': ['آزمون جامع مشاوران کسب و کار', 'آزمون آزمایشی',
                             'نمونه سوال آزمون مشاوران کسب و کار'],
                'chapter': None,
                'html': ('<p class="lead">همه سؤالات بانک، به ترتیب سرفصل. پیش از باز کردن '
                         'پاسخ‌ها، کل آزمون را در یک نشست و با زمان‌سنج پاسخ دهید تا برآورد '
                         'واقع‌بینانه‌ای از آمادگی خود به دست آورید.</p>' + ''.join(blocks)),
                'prev': None, 'next': None, 'related': [],
            })
            search_index.append({'u': '/questions/mock/', 't': f'آزمون جامع {len(allq)} سؤالی',
                                 'd': mock_desc, 'k': 'آزمون آزمایشی', 'c': 'سؤالات'})

    # Home
    home_meta, home_body = parse_fragment(
        (CONTENT / '_home.html').read_text(encoding='utf-8'), '_home.html')
    check_meta(home_meta, '_home.html')
    cards = ''.join(
        f'<li style="--ch-hue:{c["hue"]}"><a href="{c["url"]}"><b>{c["title"]}</b>'
        f'<span class="weight">{c["weightLabel"]}</span><span>{c["description"]}</span></a></li>'
        for c in chapters)
    guide_cards = ''
    if guides:
        gl = ''.join(
            f'<li><a href="{g["url"]}"><b>{g["title"]}</b><span>{g["description"]}</span></a></li>'
            for g in guides)
        guide_cards = f'<section class="topic-cards"><h2>راهنما و منابع</h2><ul>{gl}</ul></section>'
    pages.insert(0, {
        'kind': 'home', 'url': '/', 'title': home_meta['title'],
        'description': home_meta['description'], 'keywords': home_meta.get('keywords'),
        'chapter': None,
        'html': render_math(home_body, '_home.html')
                + f'<section class="chapter-cards"><h2>سرفصل‌های آزمون</h2><ul>{cards}</ul></section>'
                + guide_cards,
        'prev': None, 'next': flat[0] if flat else None, 'related': [],
    })

    for p in pages:
        write_page(p['url'], render_page(site, p, chapters, asset_urls))

    (DIST / '404.html').write_text(render_page(site, {
        'kind': 'plain', 'url': '/404.html', 'title': 'صفحه پیدا نشد',
        'description': 'صفحه‌ای که دنبال آن بودید وجود ندارد.', 'keywords': None,
        'chapter': None,
        'html': '<p>نشانی وارد شده در این سایت وجود ندارد. از فهرست کنار صفحه یا جستجو استفاده کنید.</p>'
                '<p><a href="/">بازگشت به صفحه اصلی</a></p>',
        'prev': None, 'next': None, 'related': [],
    }, chapters, asset_urls), encoding='utf-8')

    (DIST / 'search-index.json').write_text(
        json.dumps(search_index, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    def priority(u):
        return '1.0' if u == '/' else '0.8' if u.count('/') == 2 else '0.6'

    urls = ''.join(
        f'  <url><loc>{urljoin(site["siteUrl"] + "/", p["url"])}</loc>'
        f'<changefreq>monthly</changefreq><priority>{priority(p["url"])}</priority></url>\n'
        for p in pages)
    (DIST / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + urls + '</urlset>\n', encoding='utf-8')

    (DIST / 'robots.txt').write_text(
        f'User-agent: *\nAllow: /\n\nSitemap: {site["siteUrl"]}/sitemap.xml\n', encoding='utf-8')

    total_words = sum(t['words'] for c in chapters for t in c['topics'])
    print(f'✓ {len(pages)} pages  ·  {len(chapters)} chapters  ·  '
          f'{len(flat) - len(chapters)} topics'
          + (f'  ·  {len(guides)} guides' if guides else ''))
    print(f'  {total_words:,} words  ·  css {asset_urls["cssUrl"]}')
    for ch in chapters:
        w = sum(t['words'] for t in ch['topics'])
        print(f'    {ch["slug"]:<16} {len(ch["topics"]):>2} topics  {w:>6} words')
    if warnings:
        print(f'\n⚠ {len(warnings)} warning(s):')
        for w in warnings:
            print(f'  - {w}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        print(f'\n✗ build failed: {e}', file=sys.stderr)
        sys.exit(1)
