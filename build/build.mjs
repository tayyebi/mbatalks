import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import katex from 'katex';
import { renderPage } from './layout.mjs';
import { vendorAssets, copyStatic, emitJs } from './vendor.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist');
const contentDir = path.join(root, 'src/content');

const warnings = [];
const unescapeTex = (s) =>
  s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');

function parseFragment(raw, file) {
  const m = raw.match(/^\s*<!--meta\s*([\s\S]*?)-->/);
  if (!m) throw new Error(`${file}: missing <!--meta ... --> block`);
  let meta;
  try {
    meta = JSON.parse(m[1]);
  } catch (e) {
    throw new Error(`${file}: meta is not valid JSON — ${e.message}`);
  }
  return { meta, body: raw.slice(m[0].length).trim() };
}

// KaTeX has no glyph metrics for Arabic script, so Persian inside \text{} renders
// as tofu and spams the build log. Persian belongs in the figcaption instead.
const ARABIC = /[؀-ۿ]/;

function tex(raw, file, displayMode) {
  const src = unescapeTex(raw).trim();
  if (ARABIC.test(src)) {
    warnings.push(`${file}: Persian text inside a formula — move it to the caption: "${src.slice(0, 40)}…"`);
  }
  return katex.renderToString(src, { displayMode, throwOnError: false, strict: false });
}

function renderMath(html, file) {
  return html
    .replace(/<div class="math">([\s\S]*?)<\/div>/g, (_, t) => tex(t, file, true))
    .replace(/<span class="math-inline">([\s\S]*?)<\/span>/g, (_, t) => tex(t, file, false));
}

const wordCount = (html) =>
  html
    .replace(/<[^>]+>/g, ' ')
    .split(/\s+/)
    .filter(Boolean).length;

function checkMeta(meta, file, needDescription = true) {
  if (!meta.title) throw new Error(`${file}: meta.title is required`);
  if (needDescription) {
    if (!meta.description) throw new Error(`${file}: meta.description is required`);
    const n = meta.description.length;
    if (n < 80 || n > 180) warnings.push(`${file}: description is ${n} chars (aim for 120–170)`);
  }
}

async function loadContent(site) {
  const dirs = (await fs.readdir(contentDir, { withFileTypes: true }))
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort();

  const chapters = [];
  for (const dir of dirs) {
    const slug = dir.replace(/^\d+-/, '');
    const dirPath = path.join(contentDir, dir);
    const chapterFile = path.join(dirPath, '_chapter.html');
    const { meta, body } = parseFragment(await fs.readFile(chapterFile, 'utf8'), `${dir}/_chapter.html`);
    checkMeta(meta, `${dir}/_chapter.html`);

    const files = (await fs.readdir(dirPath)).filter((f) => f.endsWith('.html') && !f.startsWith('_')).sort();
    const topics = [];
    for (const f of files) {
      const raw = await fs.readFile(path.join(dirPath, f), 'utf8');
      const parsed = parseFragment(raw, `${dir}/${f}`);
      checkMeta(parsed.meta, `${dir}/${f}`);
      const tslug = parsed.meta.slug || f.replace(/^\d+-/, '').replace(/\.html$/, '');
      topics.push({
        ...parsed.meta,
        slug: tslug,
        url: `/${slug}/${tslug}/`,
        body: parsed.body,
        words: wordCount(parsed.body),
        file: `${dir}/${f}`,
      });
    }

    chapters.push({
      ...meta,
      slug,
      url: `/${slug}/`,
      body,
      topics,
      weightLabel: meta.weightLabel || (meta.weight ? `${meta.weight}` : ''),
    });
  }

  chapters.sort((a, b) => site.chapterOrder.indexOf(a.slug) - site.chapterOrder.indexOf(b.slug));
  chapters.forEach((c, i) => {
    c.hue = Math.round((i * 360) / chapters.length);
  });
  return chapters;
}

async function writePage(url, html) {
  const dir = path.join(dist, url === '/' ? '' : url);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(path.join(dir, 'index.html'), html);
}

async function main() {
  const site = JSON.parse(await fs.readFile(path.join(root, 'src/site.json'), 'utf8'));
  await fs.rm(dist, { recursive: true, force: true });
  await fs.mkdir(dist, { recursive: true });

  await copyStatic({ root, dist });
  const { cssUrl, preloadFont } = await vendorAssets({ root, dist });
  const jsUrl = await emitJs({ root, dist });
  const assets = { cssUrl, preloadFont, jsUrl };

  const chapters = await loadContent(site);
  const nav = chapters;

  // Flat reading order across the whole book, for prev/next.
  const flat = [];
  for (const ch of chapters) {
    flat.push({ url: ch.url, title: ch.title, kind: 'chapter', chapter: ch, ref: ch });
    for (const t of ch.topics) flat.push({ url: t.url, title: t.title, kind: 'topic', chapter: ch, ref: t });
  }
  const byUrl = new Map(flat.map((e) => [e.url, e]));

  const resolveRelated = (list, from) =>
    (list || [])
      .map((r) => {
        const url = `/${r.replace(/^\/|\/$/g, '')}/`;
        const hit = byUrl.get(url);
        if (!hit) warnings.push(`${from}: related link "${r}" does not resolve`);
        return hit && { url, title: hit.title };
      })
      .filter(Boolean);

  const pages = [];
  const searchIndex = [];

  for (let i = 0; i < flat.length; i++) {
    const entry = flat[i];
    const { ref, chapter, kind } = entry;
    const page = {
      kind,
      url: entry.url,
      title: ref.title,
      description: ref.description,
      keywords: ref.keywords,
      chapter,
      html: renderMath(ref.body, ref.file || chapter.slug),
      prev: i > 0 ? { url: flat[i - 1].url, title: flat[i - 1].title } : null,
      next: i < flat.length - 1 ? { url: flat[i + 1].url, title: flat[i + 1].title } : null,
      related: resolveRelated(ref.related, ref.file || `${chapter.slug}/_chapter.html`),
    };
    if (kind === 'chapter') {
      page.html += `<section class="topic-cards"><h2>مباحث این فصل</h2><ul>${chapter.topics
        .map(
          (t) =>
            `<li data-topic="${t.url}"><a href="${t.url}"><b>${t.title}</b><span>${t.description}</span></a></li>`
        )
        .join('')}</ul></section>`;
    }
    pages.push(page);
    searchIndex.push({
      u: entry.url,
      t: ref.title,
      d: ref.description,
      k: (ref.keywords || []).join(' '),
      c: kind === 'chapter' ? '' : chapter.title,
    });
  }

  // Home
  const homeRaw = await fs.readFile(path.join(contentDir, '_home.html'), 'utf8');
  const home = parseFragment(homeRaw, '_home.html');
  checkMeta(home.meta, '_home.html');
  pages.unshift({
    kind: 'home',
    url: '/',
    title: home.meta.title,
    description: home.meta.description,
    keywords: home.meta.keywords,
    chapter: null,
    html:
      renderMath(home.body, '_home.html') +
      `<section class="chapter-cards"><h2>سرفصل‌های آزمون</h2><ul>${chapters
        .map(
          (c) =>
            `<li style="--ch-hue:${c.hue}"><a href="${c.url}"><b>${c.title}</b><span class="weight">${c.weightLabel}</span><span>${c.description}</span></a></li>`
        )
        .join('')}</ul></section>`,
    prev: null,
    next: flat.length ? { url: flat[0].url, title: flat[0].title } : null,
    related: [],
  });

  for (const p of pages) await writePage(p.url, renderPage({ site, page: p, nav, assets }));

  // 404
  await fs.writeFile(
    path.join(dist, '404.html'),
    renderPage({
      site,
      page: {
        kind: 'plain',
        url: '/404.html',
        title: 'صفحه پیدا نشد',
        description: 'صفحه‌ای که دنبال آن بودید وجود ندارد.',
        chapter: null,
        html: '<p>نشانی وارد شده در این سایت وجود ندارد. از فهرست کنار صفحه یا جستجو استفاده کنید.</p><p><a href="/">بازگشت به صفحه اصلی</a></p>',
        prev: null,
        next: null,
        related: [],
      },
      nav,
      assets,
    })
  );

  await fs.writeFile(path.join(dist, 'search-index.json'), JSON.stringify(searchIndex));

  const urls = pages.map((p) => p.url);
  await fs.writeFile(
    path.join(dist, 'sitemap.xml'),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
      urls
        .map(
          (u) =>
            `  <url><loc>${new URL(u, site.siteUrl).href}</loc><changefreq>monthly</changefreq><priority>${
              u === '/' ? '1.0' : u.split('/').length === 3 ? '0.8' : '0.6'
            }</priority></url>`
        )
        .join('\n') +
      `\n</urlset>\n`
  );

  await fs.writeFile(
    path.join(dist, 'robots.txt'),
    `User-agent: *\nAllow: /\n\nSitemap: ${site.siteUrl}/sitemap.xml\n`
  );

  const totalWords = chapters.reduce((s, c) => s + c.topics.reduce((t, x) => t + x.words, 0), 0);
  console.log(`✓ ${pages.length} pages  ·  ${chapters.length} chapters  ·  ${flat.length - chapters.length} topics`);
  console.log(`  ${totalWords.toLocaleString('en-US')} words  ·  css ${cssUrl}`);
  for (const ch of chapters) {
    const w = ch.topics.reduce((t, x) => t + x.words, 0);
    console.log(`    ${ch.slug.padEnd(16)} ${String(ch.topics.length).padStart(2)} topics  ${String(w).padStart(6)} words`);
  }
  if (warnings.length) {
    console.log(`\n⚠ ${warnings.length} warning(s):`);
    for (const w of warnings) console.log(`  - ${w}`);
  }
}

main().catch((e) => {
  console.error(`\n✗ build failed: ${e.message}`);
  process.exit(1);
});
