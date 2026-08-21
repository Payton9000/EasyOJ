import { copyFile, mkdir, stat } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { build } from 'esbuild';

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(frontendRoot, '..');
const outputDirectory = resolve(projectRoot, 'app/static/vendor/codemirror');
const scriptOutput = resolve(outputDirectory, 'easyoj-editor.js');
const styleOutput = resolve(outputDirectory, 'easyoj-editor.css');

await mkdir(outputDirectory, { recursive: true });
await build({
    entryPoints: [resolve(frontendRoot, 'src/editor.mjs')],
    outfile: scriptOutput,
    bundle: true,
    format: 'iife',
    minify: true,
    target: ['es2019'],
    legalComments: 'eof',
    sourcemap: false,
});
await copyFile(resolve(frontendRoot, 'src/editor.css'), styleOutput);

const scriptSize = (await stat(scriptOutput)).size;
const styleSize = (await stat(styleOutput)).size;
console.log(`Built EasyOJ editor: ${scriptSize} byte JS, ${styleSize} byte CSS.`);
