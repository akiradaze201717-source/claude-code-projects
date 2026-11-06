import fs from 'node:fs';
import path from 'node:path';

const ASSETS = [
  'index.html',
  'privacy.html',
  'style.css',
  'app.js',
  'sw.js',
  'manifest.webmanifest',
  'icon-180.png',
  'icon-192.png',
  'icon-512.png',
  'icon.svg',
];

const outDir = path.resolve('www');
fs.mkdirSync(outDir, { recursive: true });

for (const file of ASSETS) {
  const src = path.resolve(file);
  const dest = path.join(outDir, file);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest);
  }
}

console.log(`Built ${ASSETS.length} web assets into ./www`);
