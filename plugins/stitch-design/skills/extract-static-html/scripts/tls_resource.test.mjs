import assert from 'node:assert/strict';
import test from 'node:test';
import dns from 'node:dns';
import https from 'node:https';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fetchResource, ResourceBudget } from './bounded_resources.ts';

test('TLS preserves SNI and certificate identity and never performs a rebinding lookup', async (t) => {
  const root = await mkdtemp(join(tmpdir(), 'resource-tls-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  execFileSync(
    'openssl',
    [
      'req',
      '-x509',
      '-newkey',
      'rsa:2048',
      '-nodes',
      '-days',
      '1',
      '-subj',
      '/CN=public.resource.test',
      '-addext',
      'subjectAltName=DNS:public.resource.test',
      '-keyout',
      join(root, 'key.pem'),
      '-out',
      join(root, 'cert.pem'),
    ],
    { stdio: 'ignore' },
  );
  const cert = await readFile(join(root, 'cert.pem'));
  const key = await readFile(join(root, 'key.pem'));
  const requests = [];
  const server = https.createServer({ key, cert }, (req, res) => {
    requests.push({ host: req.headers.host, sni: req.socket.servername });
    res.end('public-image');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => {
    server.closeAllConnections();
    server.close();
  });
  let lookups = 0;
  let rebind = true;
  t.mock.method(dns, 'lookup', (_host, _options, callback) => {
    lookups++;
    callback(null, [{ address: rebind && lookups > 1 ? '127.0.0.1' : '93.184.216.34', family: 4 }]);
  });
  const get = https.get;
  t.mock.method(https, 'get', (url, options, callback) => {
    assert.equal(options.agent, false);
    assert.equal(options.rejectUnauthorized, true);
    return get(
      url,
      {
        ...options,
        ca: cert,
        lookup(host, lookupOptions, done) {
          options.lookup(host, lookupOptions, (error, addresses, family) => {
            if (error) {
              done(error);
              return;
            }
            assert.ok(
              (Array.isArray(addresses) ? addresses : [{ address: addresses }]).every(
                (a) => a.address === '93.184.216.34',
              ),
            );
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
  const port = server.address().port;
  const options = () => ({ budget: new ResourceBudget(), timeout: 1000 });
  const result = await fetchResource(`https://public.resource.test:${port}/asset`, options());
  assert.equal(Buffer.from(result.split(',')[1], 'base64').toString(), 'public-image');
  assert.equal(lookups, 1);
  assert.deepEqual(requests, [
    { host: `public.resource.test:${port}`, sni: 'public.resource.test' },
  ]);
  await assert.rejects(
    fetchResource(`https://public.resource.test:${port}/next`, options()),
    /Blocked/,
  );
  assert.equal(requests.length, 1);
  rebind = false;
  await assert.rejects(fetchResource(`https://wrong.resource.test:${port}/asset`, options()), {
    code: 'ERR_TLS_CERT_ALTNAME_INVALID',
  });
  assert.equal(requests.length, 1);
});
