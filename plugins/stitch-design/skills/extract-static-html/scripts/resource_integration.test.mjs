import assert from 'node:assert/strict';
import test from 'node:test';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const artifact =
  process.env.EXTRACTOR_ARTIFACT ??
  fileURLToPath(new URL('../../../runtime/dist/extract-inline-html.mjs', import.meta.url));

async function extract(t, handler, body) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'bounded-extractor-'));
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => {
    server.closeAllConnections();
    server.close();
    await rm(root, { recursive: true, force: true });
  });
  const preload = path.join(root, 'route.mjs');
  await writeFile(
    preload,
    `import http from 'node:http';
const get = http.get;
http.get = (input, options, callback) => {
  const url = new URL(input);
  if (url.hostname !== 'resource.test') throw new Error('unexpected test destination');
  url.hostname = '127.0.0.1'; url.port = '${server.address().port}';
  return get(url, options, callback);
};`,
  );
  const source = path.join(root, 'page.jsx');
  await writeFile(source, `export default function Page() { return <div>${body}</div>; }`);
  const result = await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [
      '--import',
      preload,
      artifact,
      '--no-tailwind',
      '--timeout',
      '5000',
      '--outdir',
      root,
      '--page',
      `${source}:out.html:Test`,
    ]);
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error('extractor did not finish within fixture deadline'));
    }, 2000);
    child.stdout.resume();
    child.stderr.resume();
    child.on('error', reject);
    child.on('exit', (code) => {
      clearTimeout(timer);
      resolve(code);
    });
  });
  return { code: result, html: await readFile(path.join(root, 'out.html'), 'utf8') };
}

test('oversized declared response is rejected without draining a steady body', async (t) => {
  let chunks = 0;
  const result = await extract(
    t,
    (_req, res) => {
      res.writeHead(200, { 'Content-Length': 9 * 1024 * 1024, 'Content-Type': 'image/png' });
      res.flushHeaders();
      const timer = setInterval(() => {
        chunks++;
        res.write('x');
      }, 20);
      res.on('close', () => clearInterval(timer));
    },
    '<img src="http://resource.test/large" />',
  );
  assert.equal(result.code, 0);
  assert.ok(chunks < 10);
  assert.ok(result.html.includes('data:image/gif;base64,'));
});

test('concurrent duplicate references share one fetch and embed normally', async (t) => {
  let hits = 0;
  const result = await extract(
    t,
    (_req, res) => {
      hits++;
      res.writeHead(200, { 'Content-Type': 'image/png' });
      setTimeout(() => res.end('tiny-image'), 25);
    },
    '<img src="http://resource.test/small" /><img src="http://resource.test/small" />',
  );
  assert.equal(result.code, 0);
  assert.equal(hits, 1);
  assert.equal(result.html.match(/data:image\/png;base64,/g)?.length, 2);
});
