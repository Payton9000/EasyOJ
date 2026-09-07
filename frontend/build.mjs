import { copyFile, mkdir, readdir, rm, stat } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { build } from 'esbuild';

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(frontendRoot, '..');
const outputDirectory = resolve(projectRoot, 'app/static/vendor/codemirror');
const scriptOutput = resolve(outputDirectory, 'easyoj-editor.js');
const styleOutput = resolve(outputDirectory, 'easyoj-editor.css');

// Stale chunks from an earlier build would otherwise accumulate here.
await rm(outputDirectory, { recursive: true, force: true });
await mkdir(outputDirectory, { recursive: true });
// ESM with splitting so each language grammar becomes its own lazily fetched
// chunk instead of riding along in the main bundle.
await build({
    entryPoints: { 'easyoj-editor': resolve(frontendRoot, 'src/editor.mjs') },
    outdir: outputDirectory,
    entryNames: '[name]',
    chunkNames: 'chunks/[name]-[hash]',
    bundle: true,
    splitting: true,
    format: 'esm',
    minify: true,
    target: ['es2020'],
    legalComments: 'eof',
    sourcemap: false,
});
await copyFile(resolve(frontendRoot, 'src/editor.css'), styleOutput);

const scriptSize = (await stat(scriptOutput)).size;
const styleSize = (await stat(styleOutput)).size;
const chunkFiles = await readdir(resolve(outputDirectory, 'chunks')).catch(() => []);
console.log(
    `Built EasyOJ editor: ${scriptSize} byte entry JS, ${styleSize} byte CSS, ` +
        `${chunkFiles.length} lazy chunk(s).`
);
