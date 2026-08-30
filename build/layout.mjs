const esc = (s = '') =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// `<` inside a <script> body would end the element early regardless of JSON validity.
const jsonld = (obj) => JSON.stringify(obj).replace(/</g, '\\u003c');

function sidebar(site, nav, page) {
  const items = nav.map((ch) => {
    const current = page.chapter?.slug === ch.slug;
    const topics = current
      ? `<ul class="nav-topics">${ch.topics
          .map(
            (t) =>
              `<li><a href="${t.url}"${t.url === page.url ? ' aria-current="page"' : ''} data-topic="${esc(
                t.url
              )}">${esc(t.title)}</a></li>`
          )
          .join('')}</ul>`
      : '';
    return `<li class="nav-chapter${current ? ' is-open' : ''}" style="--ch-hue:${ch.hue}">
      <a class="nav-chapter-link" href="${ch.url}"${page.url === ch.url ? ' aria-current="page"' : ''}>
        <span class="nav-dot"></span><span class="nav-chapter-title">${esc(ch.title)}</span>
        <span class="nav-weight">${esc(ch.weightLabel)}</span>
      </a>${topics}</li>`;
  });
  return `<nav class="sidebar" id="sidebar" aria-label="فهرست کتاب">
    <p class="sidebar-heading">فهرست مطالب</p>
    <ul class="nav-list">${items.join('')}</ul>
  </nav>`;
}

function breadcrumbs(site, page) {
  if (page.kind === 'home') return '';
  const trail = [{ url: '/', title: 'خانه' }];
  if (page.chapter && page.kind !== 'chapter') trail.push({ url: page.chapter.url, title: page.chapter.title });
  const links = trail.map((t) => `<li><a href="${t.url}">${esc(t.title)}</a></li>`).join('');
  return `<nav class="crumbs" aria-label="مسیر"><ol>${links}<li aria-current="page">${esc(page.title)}</li></ol></nav>`;
}

function pager(page) {
  if (!page.prev && !page.next) return '';
  const link = (p, rel, label) =>
    p ? `<a class="pager-${rel}" rel="${rel}" href="${p.url}"><span>${label}</span><b>${esc(p.title)}</b></a>` : '<span></span>';
  return `<nav class="pager" aria-label="پیمایش">
    ${link(page.prev, 'prev', 'مبحث قبلی')}${link(page.next, 'next', 'مبحث بعدی')}
  </nav>`;
}

function structuredData(site, page, nav) {
  const abs = (u) => new URL(u, site.siteUrl).href;
  const graph = [];
  if (page.kind === 'home') {
    graph.push({
      '@type': 'WebSite',
      '@id': `${site.siteUrl}/#website`,
      url: `${site.siteUrl}/`,
      name: site.title,
      description: site.description,
      inLanguage: 'fa-IR',
      publisher: { '@id': `${site.siteUrl}/#org` },
    });
    graph.push({
      '@type': 'Organization',
      '@id': `${site.siteUrl}/#org`,
      name: site.organization,
      url: `${site.siteUrl}/`,
      logo: abs(site.logo),
    });
  } else {
    graph.push({
      '@type': page.kind === 'chapter' ? 'CollectionPage' : 'Article',
      '@id': `${abs(page.url)}#page`,
      url: abs(page.url),
      name: page.title,
      headline: page.title,
      description: page.description,
      inLanguage: 'fa-IR',
      isPartOf: { '@id': `${site.siteUrl}/#website` },
      publisher: { '@id': `${site.siteUrl}/#org` },
    });
    const trail = [{ url: '/', title: 'خانه' }];
    if (page.chapter && page.kind !== 'chapter') trail.push(page.chapter);
    trail.push(page);
    graph.push({
      '@type': 'BreadcrumbList',
      itemListElement: trail.map((t, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: t.title,
        item: abs(t.url),
      })),
    });
  }
  return jsonld({ '@context': 'https://schema.org', '@graph': graph });
}

export function renderPage({ site, page, nav, assets }) {
  const canonical = new URL(page.url, site.siteUrl).href;
  const ogImage = new URL(site.logo, site.siteUrl).href;
  const metaTitle = page.kind === 'home' ? site.title : `${page.title} | ${site.brandShort}`;

  const readToggle =
    page.kind === 'topic'
      ? `<button class="read-toggle" type="button" data-topic="${esc(page.url)}" aria-pressed="false">
           <span class="read-mark" aria-hidden="true"></span><span class="read-label">خوانده شد</span>
         </button>`
      : '';

  const related =
    page.related?.length
      ? `<section class="related"><h2>مباحث مرتبط</h2><ul>${page.related
          .map((r) => `<li><a href="${r.url}">${esc(r.title)}</a></li>`)
          .join('')}</ul></section>`
      : '';

  return `<!doctype html>
<html lang="${site.lang}" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(metaTitle)}</title>
<meta name="description" content="${esc(page.description)}">
${page.keywords?.length ? `<meta name="keywords" content="${esc(page.keywords.join('، '))}">` : ''}
<link rel="canonical" href="${canonical}">
<meta property="og:type" content="${page.kind === 'topic' ? 'article' : 'website'}">
<meta property="og:site_name" content="${esc(site.title)}">
<meta property="og:locale" content="${site.locale}">
<meta property="og:title" content="${esc(metaTitle)}">
<meta property="og:description" content="${esc(page.description)}">
<meta property="og:url" content="${canonical}">
<meta property="og:image" content="${ogImage}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="${site.logo}">
<link rel="apple-touch-icon" href="${site.logo}">
<link rel="preload" as="font" type="font/woff2" href="${assets.preloadFont}" crossorigin>
<link rel="stylesheet" href="${assets.cssUrl}">
<script>try{var t=localStorage.getItem('mba:theme');if(t)document.documentElement.dataset.theme=t}catch(e){}</script>
<script type="application/ld+json">${structuredData(site, page, nav)}</script>
</head>
<body>
<a class="skip" href="#main">پرش به محتوا</a>
<header class="topbar">
  <button class="hamburger" type="button" aria-label="فهرست" aria-expanded="false" aria-controls="sidebar"><span></span></button>
  <a class="brand" href="/">
    <img src="${site.logo}" alt="" width="36" height="36" loading="eager">
    <span>${esc(site.wordmark)}</span>
  </a>
  <div class="search">
    <input type="search" id="q" placeholder="جستجو در مباحث…" autocomplete="off" aria-label="جستجو">
    <div class="search-results" id="search-results" hidden></div>
  </div>
  <button class="theme-toggle" type="button" aria-label="تغییر پوسته"></button>
</header>
<div class="backdrop" hidden></div>
<div class="shell">
  ${sidebar(site, nav, page)}
  <main class="main" id="main">
    ${breadcrumbs(site, page)}
    <article class="prose">
      <div class="page-head">
        <h1>${esc(page.title)}</h1>
        ${readToggle}
      </div>
      ${page.html}
      ${related}
    </article>
    ${pager(page)}
  </main>
</div>
<footer class="footer">
  <p>${esc(site.title)}</p>
  <p class="footer-note">این مجموعه یک منبع مطالعاتی مستقل است و به مرجع برگزارکننده آزمون وابستگی ندارد.</p>
</footer>
<script src="${assets.jsUrl}" defer></script>
</body>
</html>
`;
}
