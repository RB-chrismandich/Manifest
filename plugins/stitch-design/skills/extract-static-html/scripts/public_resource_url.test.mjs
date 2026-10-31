import assert from 'node:assert/strict';
import test from 'node:test';
import dns from 'node:dns';
import http from 'node:http';
import https from 'node:https';
import { EventEmitter } from 'node:events';
import { isPublicAddress, isAllowedResourceUrl, publicLookup } from './public_resource_url.ts';
import { fetchResource, ResourceBudget } from './bounded_resources.ts';

const blocked = [
  '0.0.0.0',
  '10.0.0.1',
  '100.64.0.1',
  '127.1.2.3',
  '169.254.169.254',
  '172.16.0.1',
  '172.31.255.255',
  '192.0.0.8',
  '192.0.0.11',
  '192.0.2.1',
  '192.88.99.2',
  '192.168.1.1',
  '198.18.0.1',
  '198.51.100.1',
  '203.0.113.1',
  '224.0.0.1',
  '255.255.255.255',
  '::',
  '::1',
  '::127.0.0.1',
  '::ffff:7f00:1',
  '0:0:0:0:0:ffff:a00:1',
  '64:ff9b::a00:1',
  '64:ff9b:1::808:808',
  '100::1',
  '100:0:0:1::1',
  '2001::1',
  '2001:2::1',
  '2001:db8::1',
  '2002:7f00:1::1',
  '3fff::1',
  '4000::1',
  'fc00::1',
  'fd00::1',
  'fe80::1',
  'fec0::1',
  'ff02::1',
  'fe80::1%eth0',
  'garbage',
];
const allowed = [
  '8.8.8.8',
  '93.184.216.34',
  '100.63.255.255',
  '100.128.0.0',
  '172.32.0.0',
  '192.0.0.9',
  '192.0.0.10',
  '192.31.196.1',
  '192.52.193.1',
  '192.175.48.1',
  '::ffff:808:808',
  '64:ff9b::808:808',
  '64:ff9b::192.0.0.9',
  '2001:4860:4860::8888',
  '2606:4700:4700::1111',
  '2001:1::1',
  '2001:1::2',
  '2001:1::3',
  '2001:3::1',
  '2001:4:112::1',
  '2001:20::1',
  '2001:30::1',
];
test('public address policy handles binary IPv4/IPv6 forms and special ranges', () => {
  for (const address of blocked) assert.equal(isPublicAddress(address), false, address);
  for (const address of allowed) assert.equal(isPublicAddress(address), true, address);
  for (const host of [
    '2130706433',
    '0177.0.0.1',
    '0x7f000001',
    '[::ffff:127.0.0.1]',
    'localhost.',
    'a.localhost',
  ])
    assert.equal(isAllowedResourceUrl(new URL(`http://${host}/`)), false, host);
  assert.equal(isAllowedResourceUrl(new URL('file:///tmp/a')), false);
  assert.equal(isAllowedResourceUrl(new URL('https://public.resource.test/a')), true);
});
const resolve = (lookup, all = true) =>
  new Promise((accept, reject) =>
    lookup('public.resource.test', { all }, (error, address, family) =>
      error ? reject(error) : accept({ address, family }),
    ),
  );

test('DNS rejects every mixed, empty, malformed or nonpublic answer set', async (t) => {
  let answers;
  t.mock.method(dns, 'lookup', (_host, options, callback) => {
    assert.deepEqual(options, { all: true, verbatim: true });
    callback(null, answers);
  });
  for (const address of blocked.filter((a) => !['garbage', 'fe80::1%eth0'].includes(a))) {
    const bad = { address, family: address.includes(':') ? 6 : 4 };
    for (const list of [
      [bad],
      [{ address: '8.8.8.8', family: 4 }, bad],
      [bad, { address: '8.8.8.8', family: 4 }],
    ]) {
      answers = list;
      await assert.rejects(resolve(publicLookup(() => true)), /Blocked/);
    }
  }
  for (const list of [
    [],
    [{ address: 'garbage', family: 4 }],
    [{ address: '8.8.8.8', family: 6 }],
  ]) {
    answers = list;
    await assert.rejects(resolve(publicLookup(() => true)), /Blocked/);
  }
});
test('DNS snapshot is used once, preserves all public families, and fails closed on error', async (t) => {
  let calls = 0;
  t.mock.method(dns, 'lookup', (_host, _options, callback) => {
    calls++;
    callback(
      null,
      calls === 1
        ? [
            { address: '8.8.8.8', family: 4 },
            { address: '2606:4700::1111', family: 6 },
          ]
        : [{ address: '127.0.0.1', family: 4 }],
    );
  });
  assert.deepEqual((await resolve(publicLookup(() => true))).address, [
    { address: '8.8.8.8', family: 4 },
    { address: '2606:4700::1111', family: 6 },
  ]);
  assert.equal(calls, 1);
  t.mock.method(dns, 'lookup', (_host, _options, callback) => callback(new Error('DNS failed')));
  await assert.rejects(resolve(publicLookup(() => true)), /DNS failed/);
});

test('public redirects preserve Host and pin one validated lookup per socket; private redirect never connects', async (t) => {
  const hosts = [];
  const server = http.createServer((req, res) => {
    hosts.push(req.headers.host);
    if (req.url === '/public') res.writeHead(302, { Location: '/asset' });
    else if (req.url === '/private')
      res.writeHead(302, {
        Location: `http://internal.resource.test:${server.address().port}/asset`,
      });
    else if (req.url === '/literal')
      res.writeHead(302, { Location: `http://[::ffff:127.0.0.1]:${server.address().port}/asset` });
    res.end('ordinary-image');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => {
    server.closeAllConnections();
    server.close();
  });
  const calls = [];
  t.mock.method(dns, 'lookup', (host, options, callback) => {
    calls.push(host);
    callback(null, [
      { address: host === 'public.resource.test' ? '93.184.216.34' : '127.0.0.1', family: 4 },
    ]);
  });
  const get = http.get;
  t.mock.method(http, 'get', (url, options, callback) => {
    assert.equal(options.agent, false);
    const lookup = options.lookup;
    return get(
      url,
      {
        ...options,
        lookup(host, lookupOptions, done) {
          lookup(host, lookupOptions, (error, addresses, family) => {
            if (error) {
              done(error);
              return;
            }
            assert.ok(
              (Array.isArray(addresses) ? addresses : [{ address: addresses }]).every(
                (a) => a.address === '93.184.216.34',
              ),
            );
            // Route only validated public destinations to this controlled fixture.
            done(
              null,
              lookupOptions.all ? [{ address: '127.0.0.1', family: 4 }] : '127.0.0.1',
              family,
            );
          });
        },
      },
      callback,
    );
  });
  const base = `http://public.resource.test:${server.address().port}`;
  const options = () => ({ budget: new ResourceBudget(), timeout: 1000 });
  const result = await fetchResource(`${base}/public`, options());
  assert.equal(Buffer.from(result.split(',')[1], 'base64').toString(), 'ordinary-image');
  assert.equal(calls.length, 2);
  assert.deepEqual(hosts, Array(2).fill(`public.resource.test:${server.address().port}`));
  await assert.rejects(fetchResource(`${base}/private`, options()), /Blocked/);
  await assert.rejects(fetchResource(`${base}/literal`, options()), /Blocked/);
  assert.equal(hosts.length, 4);
  assert.equal(calls.length, 5);
});

test('HTTPS retains original authority and certificate validation; deadline suppresses late DNS callbacks', async (t) => {
  let late;
  let socketCallback = false;
  t.mock.method(dns, 'lookup', (_host, _options, callback) => {
    late = callback;
  });
  t.mock.method(https, 'get', (url, options) => {
    assert.equal(url.hostname, 'public.resource.test');
    assert.equal(options.agent, false);
    assert.equal(options.rejectUnauthorized, true);
    options.lookup(url.hostname, {}, () => {
      socketCallback = true;
    });
    const request = new EventEmitter();
    request.destroy = () => {};
    return request;
  });
  const budget = new ResourceBudget();
  await assert.rejects(
    fetchResource('https://public.resource.test/a', { budget, timeout: 20 }),
    /deadline/,
  );
  late(null, [{ address: '8.8.8.8', family: 4 }]);
  assert.equal(socketCallback, false);
  assert.equal(budget.aborters.size, 0);
});
