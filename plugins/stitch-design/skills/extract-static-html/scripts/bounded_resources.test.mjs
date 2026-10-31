import assert from 'node:assert/strict';
import test from 'node:test';
import http from 'node:http';
import { ResourceBudget, fetchResource, FALLBACK } from './bounded_resources.ts';
import { ResourceEmbedder } from './embed_resources.ts';

async function server(t, handler) {
  const instance = http.createServer(handler);
  await new Promise((resolve) => instance.listen(0, '127.0.0.1', resolve));
  t.after(() => {
    instance.closeAllConnections();
    instance.close();
  });
  return `http://127.0.0.1:${instance.address().port}`;
}
const options = (budget) => ({ budget, timeout: 500, isSafeUrl: () => true });
const embedder = (budget) =>
  new ResourceEmbedder({ budget, isSafeUrl: () => true, isImageUrl: () => true });

test('exact byte cap succeeds; chunked overflow aborts without retained listeners', async (t) => {
  const url = await server(t, (req, res) => {
    res.writeHead(200, { 'Content-Type': 'image/png' });
    res.write(Buffer.alloc(32));
    res.end(Buffer.alloc(req.url === '/exact' ? 32 : 33));
  });
  const budget = new ResourceBudget({ resourceBytes: 64, downloadBytes: 256 });
  const good = await fetchResource(`${url}/exact`, options(budget));
  assert.equal(Buffer.from(good.split(',')[1], 'base64').length, 64);
  await assert.rejects(fetchResource(`${url}/over`, options(budget)), /size limit/);
  assert.equal(budget.aborters.size, 0);
  assert.equal(budget.downloaded, 129);
});

test('aggregate overflow cancels active requests and prevents queued starts', async (t) => {
  let hits = 0;
  const url = await server(t, (_req, res) => {
    hits++;
    res.writeHead(200);
    const timer = setInterval(() => res.write(Buffer.alloc(8)), 5);
    res.on('close', () => clearInterval(timer));
  });
  const budget = new ResourceBudget({ resourceBytes: 64, downloadBytes: 24 });
  const engine = embedder(budget);
  const html = Array.from({ length: 8 }, (_, i) => `<img src="${url}/${i}">`).join('');
  const output = await engine.embed(html, 2, 500);
  assert.ok(budget.closed);
  assert.ok(budget.downloaded <= 24);
  assert.ok(hits <= 2);
  assert.equal(budget.aborters.size, 0);
  assert.equal(output.match(/data:image\/gif/g)?.length, 8);
});

test('redirect/error bodies are destroyed and redirects retain the original alias', async (t) => {
  let closed = 0;
  const url = await server(t, (req, res) => {
    if (req.url === '/asset') {
      res.writeHead(200, { 'Content-Type': 'font/woff2' });
      res.end('font');
      return;
    }
    res.writeHead(req.url === '/redirect' ? 302 : 500, { Location: '/asset' });
    res.flushHeaders();
    const timer = setInterval(() => res.write('x'), 5);
    res.on('close', () => {
      clearInterval(timer);
      closed++;
    });
  });
  const engine = embedder(new ResourceBudget());
  const output = await engine.embed(
    `<img src="${url}/redirect"><video poster="${url}/error">`,
    2,
    500,
  );
  assert.ok(output.includes('data:font/woff2;base64,'));
  assert.ok(output.includes(FALLBACK));
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(closed, 2);
});

test('wall clock deadline stops steady streams, and abrupt responses settle', async (t) => {
  const url = await server(t, (req, res) => {
    res.writeHead(200);
    res.write('x');
    if (req.url === '/broken') {
      setTimeout(() => res.destroy(), 5);
      return;
    }
    const timer = setInterval(() => res.write('x'), 5);
    res.on('close', () => clearInterval(timer));
  });
  const budget = new ResourceBudget();
  await assert.rejects(
    fetchResource(`${url}/trickle`, { ...options(budget), timeout: 40 }),
    /deadline/,
  );
  await assert.rejects(fetchResource(`${url}/broken`, options(budget)));
  assert.equal(budget.aborters.size, 0);
});

test('cache and request counts stay bounded across pages and redirect loops', async (t) => {
  let hits = 0;
  const url = await server(t, (req, res) => {
    hits++;
    if (req.url === '/loop') {
      res.writeHead(302, { Location: '/loop' });
      res.end();
    } else res.end('ok');
  });
  const budget = new ResourceBudget({ requests: 2 });
  const engine = embedder(budget);
  await engine.embed(`<img src="${url}/first">`, 2, 500);
  await engine.embed(`<img src="${url}/second"><img src="${url}/third">`, 2, 500);
  assert.ok(engine.cache.size <= 2);
  assert.ok(hits <= 2);
  const loopBudget = new ResourceBudget();
  await assert.rejects(fetchResource(`${url}/loop`, options(loopBudget)), /redirect limit/);
  assert.equal(loopBudget.aborters.size, 0);
});

test('repeated src, CSS and poster replacements are checked before assembly', async (t) => {
  const url = await server(t, (_req, res) => res.end(Buffer.alloc(60)));
  const budget = new ResourceBudget({ pageBytes: 400, outputBytes: 500 });
  const engine = embedder(budget);
  const source = `<img src="${url}/a"><style>x{background:url('${url}/a')}</style><video poster="${url}/a"><img src="${url}/a">`;
  await assert.rejects(engine.embed(source, 3, 500), /output size/);
  assert.equal(engine.cache.size, 1);
  assert.equal(budget.output, 0);
});

test('UTF-8 bytes and cumulative output are bounded, including cache-only pages', async (t) => {
  const budget = new ResourceBudget({ pageBytes: 100, outputBytes: 120 });
  const engine = embedder(budget);
  assert.equal(await engine.embed('é'.repeat(40), 2, 500), 'é'.repeat(40));
  await assert.rejects(engine.embed('é'.repeat(21), 2, 500), /output size/);
  assert.equal(budget.output, 80);
});

test('missing content type, empty assets and existing application font MIME remain supported', async (t) => {
  const url = await server(t, (req, res) => {
    if (req.url === '/font') res.setHeader('Content-Type', 'application/font-woff');
    res.end(req.url === '/empty' ? '' : 'bytes');
  });
  const engine = embedder(new ResourceBudget());
  const output = await engine.embed(
    `<img src="${url}/empty"><style>x{src:url('${url}/font')}</style>`,
    2,
    500,
  );
  assert.ok(output.includes('data:image/jpeg;base64,'));
  assert.ok(output.includes('data:application/font-woff;base64,'));
});

test('later shrinking replacements permit a page whose final size fits', async (t) => {
  const url = await server(t, (req, res) => res.end(req.url === '/a' ? Buffer.alloc(60) : ''));
  const budget = new ResourceBudget({ pageBytes: 270 });
  const engine = embedder(budget);
  const source = `<img src="${url}/a"><img src="${url}/${'b'.repeat(140)}">`;
  const output = await engine.embed(source, 2, 500);
  assert.ok(Buffer.byteLength(output) < 270);
  assert.equal(budget.output, Buffer.byteLength(output));
});

test('overlapping CSS syntax inside a src URL cannot corrupt output accounting', async (t) => {
  let hits = 0;
  const url = await server(t, (_req, res) => {
    hits++;
    res.end('asset');
  });
  const budget = new ResourceBudget();
  const engine = embedder(budget);
  const source = `<img src="${url}/a?x=url(${url}/b)&y=url(${url}/c)">`;
  const output = await engine.embed(source, 2, 500);
  assert.equal(hits, 1);
  assert.equal(output, '<img src="data:image/jpeg;base64,YXNzZXQ=">');
  assert.equal(budget.output, Buffer.byteLength(output));
});

test('encoding and reference limits reject before allocating output', async (t) => {
  const url = await server(t, (_req, res) => res.end('1234567890'));
  const budget = new ResourceBudget({ encodedBytes: 10 });
  await assert.rejects(fetchResource(url, options(budget)), /Aggregate/);
  assert.equal(budget.encoded, 0);
  assert.equal(budget.aborters.size, 0);
  const engine = embedder(new ResourceBudget({ references: 2 }));
  await assert.rejects(engine.embed('url(a)url(b)url(c)', 1, 500), /reference limit/);
});
