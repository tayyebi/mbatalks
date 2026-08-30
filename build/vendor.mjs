import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const hash8 = (buf) => createHash('sha256').update(buf).digest('hex').slice(0, 8);

// Vazirmatn FD renders Latin digits as Persian glyphs; the plain face is used for
// .en / code so "ISO 26000" keeps Latin digits. See the digit policy in the plan.
const VAZIR = [
  { file: 'misc/Farsi-Digits/fonts/webfonts/Vazirmatn-FD-Regular.woff2', family: 'Vazirmatn FD', weight: 400 },
  { file: 'misc/Farsi-Digits/fonts/webfonts/Vazirmatn-FD-Medium.woff2', family: 'Vazirmatn FD', weight: 500 },
  { file: 'misc/Farsi-Digits/fonts/webfonts/Vazirmatn-FD-Bold.woff2', family: 'Vazirmatn FD', weight: 700 },
  { file: 'fonts/webfonts/Vazirmatn-Regular.woff2', family: 'Vazirmatn', weight: 400 },
  { file: 'fonts/webfonts/Vazirmatn-Bold.woff2', family: 'Vazirmatn', weight: 700 },
];

async function emitFont(srcPath, outDir) {
  const buf = await fs.readFile(srcPath);
  const base = path.basename(srcPath, '.woff2');
  const name = `${base}.${hash8(buf)}.woff2`;
  await fs.writeFile(path.join(outDir, name), buf);
  return `/static/fonts/${name}`;
}

export async function vendorAssets({ root, dist }) {
  const fontsOut = path.join(dist, 'static', 'fonts');
  const cssOut = path.join(dist, 'static', 'css');
  await fs.mkdir(fontsOut, { recursive: true });
  await fs.mkdir(cssOut, { recursive: true });

  // --- Vazirmatn ---------------------------------------------------------
  const faces = [];
  let preload = null;
  for (const f of VAZIR) {
    const url = await emitFont(path.join(root, 'node_modules/vazirmatn', f.file), fontsOut);
    if (f.family === 'Vazirmatn FD' && f.weight === 400) preload = url;
    faces.push(
      `@font-face{font-family:"${f.family}";font-style:normal;font-weight:${f.weight};` +
        `font-display:swap;src:url(${url}) format("woff2")}`
    );
  }

  // --- KaTeX -------------------------------------------------------------
  const katexDir = path.join(root, 'node_modules/katex/dist');
  const katexFonts = (await fs.readdir(path.join(katexDir, 'fonts'))).filter((f) => f.endsWith('.woff2'));
  const katexMap = new Map();
  for (const f of katexFonts) {
    katexMap.set(f, await emitFont(path.join(katexDir, 'fonts', f), fontsOut));
  }

  // katex-swap ships font-display:swap, avoiding invisible formulas during load.
  let katexCss = await fs.readFile(path.join(katexDir, 'katex-swap.min.css'), 'utf8');
  // Drop the legacy .woff/.ttf fallbacks: every target browser has woff2 and
  // these would otherwise 404 against paths we never emit.
  katexCss = katexCss.replace(/,url\(fonts\/[^)]+\.(?:woff|ttf)\)\s*format\("(?:woff|truetype)"\)/g, '');
  katexCss = katexCss.replace(/url\(fonts\/([\w-]+\.woff2)\)/g, (m, name) => {
    const url = katexMap.get(name);
    if (!url) throw new Error(`KaTeX css references a missing font: ${name}`);
    return `url(${url})`;
  });

  // --- one hashed stylesheet --------------------------------------------
  const main = await fs.readFile(path.join(root, 'src/css/main.css'), 'utf8');
  const bundle = `${faces.join('\n')}\n${katexCss}\n${main}`;
  const cssName = `site.${hash8(Buffer.from(bundle))}.css`;
  await fs.writeFile(path.join(cssOut, cssName), bundle);

  return { cssUrl: `/static/css/${cssName}`, preloadFont: preload };
}

export async function copyStatic({ root, dist }) {
  await fs.cp(path.join(root, 'static'), path.join(dist, 'static'), { recursive: true });
}

export async function emitJs({ root, dist }) {
  const js = await fs.readFile(path.join(root, 'src/js/app.js'), 'utf8');
  const name = `app.${hash8(Buffer.from(js))}.js`;
  const out = path.join(dist, 'static', 'js');
  await fs.mkdir(out, { recursive: true });
  await fs.writeFile(path.join(out, name), js);
  return `/static/js/${name}`;
}
