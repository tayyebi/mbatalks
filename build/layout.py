"""Page template: meta tags, JSON-LD, sidebar, breadcrumbs, pager."""

import json
from html import escape as _e
from urllib.parse import urljoin


CURRENT = ' aria-current="page"'


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
        items.append(
            f'<li class="nav-chapter{" is-open" if current else ""}" style="--ch-hue:{ch["hue"]}">\n'
            f'      <a class="nav-chapter-link" href="{ch["url"]}"'
            f'{CURRENT if page["url"] == ch["url"] else ""}>\n'
            f'        <span class="nav-dot"></span><span class="nav-chapter-title">{esc(ch["title"])}</span>\n'
            f'        <span class="nav-weight">{esc(ch["weightLabel"])}</span>\n'
            f'      </a>{topics}</li>'
        )
    return (
        '<nav class="sidebar" id="sidebar" aria-label="فهرست کتاب">\n'
        '    <p class="sidebar-heading">فهرست مطالب</p>\n'
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

    def link(p, rel, label):
        if not p:
            return '<span></span>'
        return (f'<a class="pager-{rel}" rel="{rel}" href="{p["url"]}">'
                f'<span>{label}</span><b>{esc(p["title"])}</b></a>')

    return ('<nav class="pager" aria-label="پیمایش">\n    '
            + link(page['prev'], 'prev', 'مبحث قبلی')
            + link(page['next'], 'next', 'مبحث بعدی')
            + '\n  </nav>')


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

    read_toggle = ''
    if page['kind'] == 'topic':
        read_toggle = (
            f'<button class="read-toggle" type="button" data-topic="{esc(page["url"])}" aria-pressed="false">\n'
            '           <span class="read-mark" aria-hidden="true"></span>'
            '<span class="read-label">خوانده شد</span>\n         </button>'
        )

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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(meta_title)}</title>
<meta name="description" content="{esc(page['description'])}">
{keywords}
<link rel="canonical" href="{canonical}">
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
<header class="topbar">
  <button class="hamburger" type="button" aria-label="فهرست" aria-expanded="false" aria-controls="sidebar"><span></span></button>
  <a class="brand" href="/">
    <img src="{site['logo']}" alt="" width="36" height="36" loading="eager">
    <span>{esc(site['wordmark'])}</span>
  </a>
  <div class="search">
    <input type="search" id="q" placeholder="جستجو در مباحث…" autocomplete="off" aria-label="جستجو">
    <div class="search-results" id="search-results" hidden></div>
  </div>
  <button class="theme-toggle" type="button" aria-label="تغییر پوسته"></button>
</header>
<div class="backdrop" hidden></div>
<div class="shell">
  {sidebar(nav, page)}
  <main class="main" id="main">
    {breadcrumbs(page)}
    <article class="prose">
      <div class="page-head">
        <h1>{esc(page['title'])}</h1>
        {read_toggle}
      </div>
      {page['html']}
      {related}
    </article>
    {pager(page)}
  </main>
</div>
<footer class="footer">
  <p>{esc(site['title'])}</p>
  <p class="footer-note">این مجموعه یک منبع مطالعاتی مستقل است و به مرجع برگزارکننده آزمون وابستگی ندارد.</p>
</footer>
<script src="{assets['jsUrl']}" defer></script>
</body>
</html>
'''
