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

for (const kind of ['private DNS', 'mapped IPv6']) {
  test(`${kind} never reaches the controlled internal fixture`, async (t) => {
    const root = await mkdtemp(path.join(os.tmpdir(), 'ssrf-extractor-'));
    let hits = 0;
    const server = http.createServer((_req, res) => {
      hits++;
      res.end('internal-fixture-only');
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    t.after(async () => {
      server.closeAllConnections();
      server.close();
      await rm(root, { recursive: true, force: true });
    });
    const preload = path.join(root, 'dns.mjs');
    await writeFile(
      preload,
      `import dns from 'node:dns';
dns.lookup = (hostname, options, callback) => {
  if (hostname !== 'internal.resource.test') throw new Error('unexpected DNS destination');
  if (options.all) callback(null, [{address:'127.0.0.1',family:4}]);
  else callback(null, '127.0.0.1', 4);
};`,
    );
    const host = kind === 'private DNS' ? 'internal.resource.test' : '[::ffff:127.0.0.1]';
    const source = path.join(root, 'page.jsx');
    await writeFile(
      source,
      `export default function Page(){return <img src="http://${host}:${server.address().port}/asset"/>;}`,
    );
    const code = await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [
        '--import',
        preload,
        artifact,
        '--no-tailwind',
        '--outdir',
        root,
        '--page',
        `${source}:out.html:Test`,
      ]);
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error('fixture deadline'));
      }, 2000);
      child.stdout.resume();
      child.stderr.resume();
      child.on('error', reject);
      child.on('exit', (status) => {
        clearTimeout(timer);
        resolve(status);
      });
    });
    assert.equal(code, 0);
    assert.equal(hits, 0);
    const html = await readFile(path.join(root, 'out.html'), 'utf8');
    assert.ok(!html.includes(Buffer.from('internal-fixture-only').toString('base64')));
  });
}
