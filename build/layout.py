"""Page template: meta tags, JSON-LD, sidebar, breadcrumbs, pager."""

import json
from html import escape as _e
from urllib.parse import urljoin


CURRENT = ' aria-current="page"'

# Inline SVG keeps the icons under the site's CSP (no icon font, no extra request).
ICON = {
    'search': '<circle cx="11" cy="11" r="7"></circle><path d="M20 20l-4.5-4.5"></path>',
    'close': '<path d="M6 6l12 12M18 6L6 18"></path>',
    'prev': '<path d="M9 5l7 7-7 7"></path>',   # RTL: back is toward the right
    'next': '<path d="M15 5l-7 7 7 7"></path>',
    'top': '<path d="M12 20V6"></path><path d="M5 13l7-7 7 7"></path>',
}

# Persian digits everywhere, including counts the build generates.
FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa_num(n):
    return str(n).translate(FA_DIGITS)


def icon(name, cls='icon'):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true" '
            f'focusable="false">{ICON[name]}</svg>')


def esc(s=''):
    return _e('' if s is None else str(s), quote=True)


def jsonld(obj):
    # `<` inside a <script> body would end the element early regardless of JSON validity.
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def abs_url(site, u):
    return urljoin(site['siteUrl'] + '/', u)


def sidebar(nav, page):
    items = []
    for ch in nav:
        current = page['chapter'] is not None and page['chapter']['slug'] == ch['slug']
        topics = ''
        if current:
            lis = ''.join(
                f'<li><a href="{t["url"]}"'
                f'{CURRENT if t["url"] == page["url"] else ""}'
                f' data-topic="{esc(t["url"])}">{esc(t["title"])}</a></li>'
                for t in ch['topics']
            )
            topics = f'<ul class="nav-topics">{lis}</ul>'
        # The hue lives in a generated class, not a style attribute: the site's
        # CSP has no 'unsafe-inline' for styles, so inline ones never applied.
        items.append(
            f'<li class="nav-chapter ch-{ch["slug"]}{" is-open" if current else ""}">\n'
            f'      <a class="nav-chapter-link" href="{ch["url"]}"'
            f' data-chapter="{ch["url"]}" data-topics="{len(ch["topics"])}"'
            f'{CURRENT if page["url"] == ch["url"] else ""}>\n'
            f'        <span class="nav-dot"></span><span class="nav-chapter-title">{esc(ch["title"])}</span>\n'
            f'        <span class="nav-weight">{esc(ch["weightLabel"])}</span>\n'
            f'      </a><div class="meter" aria-hidden="true"><i></i></div>{topics}</li>'
        )
    total = sum(len(ch['topics']) for ch in nav)
    return (
        '<nav class="sidebar" id="sidebar" aria-label="فهرست کتاب">\n'
        '    <div class="sidebar-top">\n'
        '      <p class="sidebar-heading">فهرست مطالب</p>\n'
        '      <button class="icon-btn drawer-close" type="button" aria-label="بستن فهرست">'
        + icon('close') + '</button>\n'
        '    </div>\n'
        f'    <div class="book-progress" data-total="{total}">\n'
        '      <p class="book-progress-label"><span>پیشرفت مطالعه</span>'
        f'<span class="book-progress-count">{fa_num(0)} از {fa_num(total)} مبحث</span></p>\n'
        '      <div class="meter" aria-hidden="true"><i></i></div>\n'
        '    </div>\n'
        f'    <ul class="nav-list">{"".join(items)}</ul>\n'
        '  </nav>'
    )


def breadcrumbs(page):
    if page['kind'] == 'home':
        return ''
    trail = [{'url': '/', 'title': 'خانه'}]
    if page['chapter'] and page['kind'] != 'chapter':
        trail.append(page['chapter'])
    links = ''.join(f'<li><a href="{t["url"]}">{esc(t["title"])}</a></li>' for t in trail)
    return (f'<nav class="crumbs" aria-label="مسیر"><ol>{links}'
            f'<li aria-current="page">{esc(page["title"])}</li></ol></nav>')


def pager(page):
    if not page['prev'] and not page['next']:
        return ''

    def link(p, rel):
        if not p:
            return '<span></span>'
        chapter = p.get('kind') == 'chapter'
        label = ('فصل ' if chapter else 'مبحث ') + ('بعدی' if rel == 'next' else 'قبلی')
        return (f'<a class="pager-{rel}" rel="{rel}" href="{p["url"]}">'
                f'{icon(rel, "chev")}'
                f'<span class="pager-text"><span>{label}</span>'
                f'<b>{esc(p["title"])}</b></span></a>')

    position = ''
    if page.get('position'):
        i, n = page['position']
        position = (f'<p class="pager-pos">مبحث {fa_num(i)} از {fa_num(n)} در فصل '
                    f'«{esc(page["chapter"]["title"])}»</p>')

    return ('<div class="pager-wrap">' + position
            + '<nav class="pager" aria-label="پیمایش">\n    '
            + link(page['prev'], 'prev')
            + link(page['next'], 'next')
            + '\n    </nav></div>')


def structured_data(site, page):
    graph = []
    if page['kind'] == 'home':
        graph.append({
            '@type': 'WebSite',
            '@id': f'{site["siteUrl"]}/#website',
            'url': f'{site["siteUrl"]}/',
            'name': site['title'],
            'description': site['description'],
            'inLanguage': 'fa-IR',
            'publisher': {'@id': f'{site["siteUrl"]}/#org'},
        })
        graph.append({
            '@type': 'Organization',
            '@id': f'{site["siteUrl"]}/#org',
            'name': site['organization'],
            'url': f'{site["siteUrl"]}/',
            'logo': abs_url(site, site['logo']),
        })
    else:
        graph.append({
            '@type': 'CollectionPage' if page['kind'] == 'chapter' else 'Article',
            '@id': f'{abs_url(site, page["url"])}#page',
            'url': abs_url(site, page['url']),
            'name': page['title'],
            'headline': page['title'],
            'description': page['description'],
            'inLanguage': 'fa-IR',
            'isPartOf': {'@id': f'{site["siteUrl"]}/#website'},
            'publisher': {'@id': f'{site["siteUrl"]}/#org'},
        })
        trail = [{'url': '/', 'title': 'خانه'}]
        if page['chapter'] and page['kind'] != 'chapter':
            trail.append(page['chapter'])
        trail.append(page)
        graph.append({
            '@type': 'BreadcrumbList',
            'itemListElement': [
                {'@type': 'ListItem', 'position': i + 1, 'name': t['title'],
                 'item': abs_url(site, t['url'])}
                for i, t in enumerate(trail)
            ],
        })
    return jsonld({'@context': 'https://schema.org', '@graph': graph})


def render_page(site, page, nav, assets):
    canonical = abs_url(site, page['url'])
    og_image = abs_url(site, site['logo'])
    meta_title = site['title'] if page['kind'] == 'home' else f'{page["title"]} | {site["brandShort"]}'

    meta_bits = []
    if page.get('minutes'):
        meta_bits.append(f'<span class="meta-time">{fa_num(page["minutes"])} دقیقه مطالعه</span>')
    if page['kind'] == 'topic':
        if meta_bits:
            meta_bits.append('<span class="dot" aria-hidden="true">·</span>')
        meta_bits.append(
            f'<button class="read-toggle" type="button" data-topic="{esc(page["url"])}"'
            f' data-title="{esc(page["title"])}" aria-pressed="false">'
            '<span class="read-mark" aria-hidden="true"></span>'
            '<span class="read-label">خوانده شد</span></button>'
        )
    page_meta = f'<div class="page-meta">{"".join(meta_bits)}</div>' if meta_bits else ''

    # Filled in by app.js from the reader's own history; empty without JS.
    resume = '<div class="resume" id="resume" hidden></div>' if page['kind'] == 'home' else ''

    # Keep scrolling past the end of the text and this fills up, then follows
    # the "next" link — reading the book straight through without aiming at it.
    continue_panel = ''
    if page.get('next'):
        continue_panel = (
            '<div class="continue" aria-hidden="true" hidden>'
            '<span class="continue-label">ادامه</span>'
            f'<b class="continue-title">{esc(page["next"]["title"])}</b>'
            '<span class="meter"><i></i></span></div>'
        )

    rel_links = ''.join(
        f'<link rel="{rel}" href="{abs_url(site, page[rel]["url"])}">'
        for rel in ('prev', 'next') if page.get(rel))

    related = ''
    if page.get('related'):
        lis = ''.join(f'<li><a href="{r["url"]}">{esc(r["title"])}</a></li>' for r in page['related'])
        related = f'<section class="related"><h2>مباحث مرتبط</h2><ul>{lis}</ul></section>'

    keywords = ''
    if page.get('keywords'):
        keywords = f'<meta name="keywords" content="{esc("، ".join(page["keywords"]))}">'

    return f'''<!doctype html>
<html lang="{site['lang']}" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(meta_title)}</title>
<meta name="description" content="{esc(page['description'])}">
{keywords}
<link rel="canonical" href="{canonical}">
{rel_links}
<meta property="og:type" content="{'article' if page['kind'] == 'topic' else 'website'}">
<meta property="og:site_name" content="{esc(site['title'])}">
<meta property="og:locale" content="{site['locale']}">
<meta property="og:title" content="{esc(meta_title)}">
<meta property="og:description" content="{esc(page['description'])}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="{site['logo']}">
<link rel="apple-touch-icon" href="{site['logo']}">
<link rel="preload" as="font" type="font/woff2" href="{assets['preloadFont']}" crossorigin>
<link rel="stylesheet" href="{assets['cssUrl']}">
<script>try{{var t=localStorage.getItem('mba:theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<script type="application/ld+json">{structured_data(site, page)}</script>
</head>
<body>
<a class="skip" href="#main">پرش به محتوا</a>
<header class="topbar" id="topbar">
  <button class="icon-btn hamburger" type="button" aria-label="فهرست" aria-expanded="false" aria-controls="sidebar"><span></span></button>
  <a class="brand" href="/">
    <img src="{site['logo']}" alt="" width="36" height="36" loading="eager">
    <span>{esc(site['wordmark'])}</span>
  </a>
  <span class="topbar-spacer"></span>
  <button class="icon-btn search-toggle" type="button" aria-label="جستجو" aria-expanded="false" aria-controls="q">{icon('search')}</button>
  <div class="search">
    <input type="search" id="q" placeholder="جستجو در مباحث…" autocomplete="off" aria-label="جستجو">
    <button class="icon-btn search-close" type="button" aria-label="بستن جستجو">{icon('close')}</button>
    <div class="search-results" id="search-results" hidden></div>
  </div>
  <button class="icon-btn theme-toggle" type="button" aria-label="تغییر پوسته"></button>
  <div class="progress" aria-hidden="true"><i></i></div>
</header>
<div class="backdrop" hidden></div>
<div class="shell">
  {sidebar(nav, page)}
  <main class="main" id="main">
    {breadcrumbs(page)}
    {resume}
    <article class="prose">
      <div class="page-head">
        <h1>{esc(page['title'])}</h1>
        {page_meta}
      </div>
      {page['html']}
      {related}
    </article>
    {pager(page)}
  </main>
</div>
{continue_panel}
<button class="icon-btn to-top" type="button" aria-label="بازگشت به ابتدای صفحه" hidden>{icon('top')}</button>
<footer class="footer">
  <p>{esc(site['title'])}</p>
  <p class="footer-note">این مجموعه یک منبع مطالعاتی مستقل است و به مرجع برگزارکننده آزمون وابستگی ندارد.</p>
</footer>
<script src="{assets['jsUrl']}" defer></script>
</body>
</html>
'''
