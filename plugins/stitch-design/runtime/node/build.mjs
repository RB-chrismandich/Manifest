#!/usr/bin/env node
/** Build deterministic, standalone Stitch runtime artifacts. */

import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const nodeRoot = path.dirname(fileURLToPath(import.meta.url));
const bundleRoot = path.resolve(nodeRoot, '../..');
const committedDist = path.join(bundleRoot, 'runtime/dist');
const checkMode = process.argv.includes('--check');
const notice = `THIRD-PARTY LICENSE NOTICES
esbuild - MIT - https://github.com/evanw/esbuild
@babel/parser, @babel/traverse, @babel/generator - MIT - https://github.com/babel/babel
puppeteer-core - Apache-2.0 - https://github.com/puppeteer/puppeteer
These build-time packages are bundled into generated artifacts where required.
`;
const banner = `import { createRequire as __manifestCreateRequire } from 'node:module';
const require = __manifestCreateRequire(import.meta.url);
/*
${notice}*/`;

const entries = [
  ['extract-inline-html.mjs', 'skills/extract-static-html/scripts/extract_inline_html.ts'],
  ['post-process.mjs', 'skills/extract-static-html/scripts/post_process.ts'],
  ['snapshot.mjs', 'skills/extract-static-html/scripts/snapshot.ts'],
];

const cdpOnlyPlugin = {
  name: 'manifest-cdp-only',
  setup(buildContext) {
    buildContext.onResolve({ filter: /\/bidi\/bidi\.js$/ }, () => ({
      path: 'bidi-disabled',
      namespace: 'manifest-cdp-only',
    }));
    buildContext.onLoad({ filter: /.*/, namespace: 'manifest-cdp-only' }, () => ({
      contents: `
export async function connectBidiOverCdp() {
  throw new Error('WebDriver BiDi is not included in the Manifest Chromium snapshot runtime');
}
export const BidiBrowser = { create: connectBidiOverCdp };
`,
      loader: 'js',
    }));
  },
};

const validatorSource = String.raw`
import { parse } from '@babel/parser';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HEX_COLOR_REGEX = /#[0-9A-Fa-f]{3,8}\b/;
const RGBA_COLOR_REGEX = /^rgba?\(\s*\d/;
const HTML_ELEMENTS = new Set(['div','span','p','h1','h2','h3','h4','h5','h6','img','button','a','input','ul','ol','li','section','header','footer','nav','main']);

function walk(node, parent, visit) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const child of node) walk(child, parent, visit);
    return;
  }
  if (typeof node.type === 'string') visit(node, parent);
  for (const [key, child] of Object.entries(node)) {
    if (key !== 'loc' && key !== 'start' && key !== 'end') walk(child, node, visit);
  }
}

export function validateFile(filePath, { native = false } = {}) {
  if (!filePath) throw new Error('component path is required');
  const code = fs.readFileSync(filePath, 'utf8');
  const ast = parse(code, {
    sourceType: 'module',
    errorRecovery: false,
    plugins: ['typescript', 'jsx'],
  });
  let hasInterface = false;
  let hasExportedInterface = false;
  const colors = [];
  const htmlElements = [];
  walk(ast, null, (node, parent) => {
    if (node.type === 'TSInterfaceDeclaration' && node.id?.name?.endsWith('Props')) {
      hasInterface = true;
      if (parent?.type === 'ExportNamedDeclaration') hasExportedInterface = true;
    }
    if (node.type === 'StringLiteral') {
      if (HEX_COLOR_REGEX.test(node.value) || (native && RGBA_COLOR_REGEX.test(node.value))) {
        colors.push(node.value);
      }
    }
    if (native && node.type === 'JSXOpeningElement' && node.name?.type === 'JSXIdentifier' && HTML_ELEMENTS.has(node.name.name)) {
      htmlElements.push(node.name.name);
    }
  });
  const validInterface = native ? hasExportedInterface : hasInterface;
  const valid = validInterface && colors.length === 0 && htmlElements.length === 0;
  console.log('--- Validation for: ' + path.basename(filePath) + ' ---');
  console.log(validInterface ? 'PASS: Props interface found.' : 'FAIL: Missing required Props interface.');
  if (colors.length) console.error('FAIL: hardcoded colors: ' + colors.join(', '));
  if (htmlElements.length) console.error('FAIL: HTML elements: ' + [...new Set(htmlElements)].join(', '));
  console.log(valid ? '\nCOMPONENT VALID.' : '\nVALIDATION FAILED.');
  return valid;
}

function main(argv) {
  if (argv.includes('--help')) {
    console.log('Usage: node validate-react.mjs [--native] <component.tsx>');
    return 0;
  }
  const native = argv.includes('--native');
  const filePath = argv.find((arg) => arg !== '--native');
  try {
    return validateFile(filePath, { native }) ? 0 : 1;
  } catch (error) {
    console.error('ERROR:', error.message);
    return 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2));
}
`;

async function emit(outdir) {
  await fs.mkdir(outdir, { recursive: true });
  const buildOptions = {
    bundle: true,
    platform: 'node',
    format: 'esm',
    target: 'node20',
    nodePaths: [path.join(nodeRoot, 'node_modules')],
    legalComments: 'none',
    minify: true,
    banner: { js: banner },
  };
  for (const [outfile, entry] of entries) {
    await build({
      ...buildOptions,
      entryPoints: [path.join(bundleRoot, entry)],
      outfile: path.join(outdir, outfile),
      plugins: outfile === 'snapshot.mjs' ? [cdpOnlyPlugin] : [],
    });
  }
  const scratch = path.join(outdir, '.validate-react-source.mjs');
  await fs.writeFile(scratch, validatorSource, 'utf8');
  await build({
    ...buildOptions,
    entryPoints: [scratch],
    outfile: path.join(outdir, 'validate-react.mjs'),
  });
  await fs.rm(scratch);
}

async function digest(file) {
  return createHash('sha256').update(await fs.readFile(file)).digest('hex');
}

async function check(rebuilt) {
  const mismatches = [];
  for (const [name] of [...entries, ['validate-react.mjs']]) {
    const committed = path.join(committedDist, name);
    try {
      if ((await digest(committed)) !== (await digest(path.join(rebuilt, name)))) {
        mismatches.push(name);
      }
    } catch {
      mismatches.push(name);
    }
  }
  if (mismatches.length) {
    throw new Error(`generated Stitch runtime drift: ${mismatches.join(', ')}`);
  }
}

if (checkMode) {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'stitch-build-'));
  try {
    await emit(temporary);
    await check(temporary);
  } finally {
    await fs.rm(temporary, { recursive: true, force: true });
  }
} else {
  await emit(committedDist);
}
