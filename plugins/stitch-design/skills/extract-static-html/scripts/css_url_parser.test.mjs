import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';

import { extractCssUrls } from './css_url_parser.ts';

// (input, expected extractCssUrls output). Expected values are derived from
// the parser contract: quoted/unquoted values, escaped characters, whitespace
// inside parens, data: URLs, and malformed url( tokens are all handled
// character-by-character without regex.
const CASES = [
  // Quoted values, single and double.
  ["url('a.png')", [{ url: 'a.png', fullMatch: "url('a.png')", start: 0, end: 12 }]],
  ['url("b.png")', [{ url: 'b.png', fullMatch: 'url("b.png")', start: 0, end: 12 }]],
  // Unquoted value.
  ['url(c.png)', [{ url: 'c.png', fullMatch: 'url(c.png)', start: 0, end: 10 }]],
  // Whitespace inside the parens, unquoted.
  ['url( d.png )', [{ url: 'd.png', fullMatch: 'url( d.png )', start: 0, end: 12 }]],
  // Empty values are still real matches.
  ['url()', [{ url: '', fullMatch: 'url()', start: 0, end: 5 }]],
  ['url(  )', [{ url: '', fullMatch: 'url(  )', start: 0, end: 7 }]],
  // Backslash escapes inside a quoted value collapse to the literal char.
  ["url('a\\'b.png')", [{ url: "a'b.png", fullMatch: "url('a\\'b.png')", start: 0, end: 15 }]],
  // data: URLs are matched like any other url().
  [
    'url(data:image/png;base64,AAAA)',
    [{ url: 'data:image/png;base64,AAAA', fullMatch: 'url(data:image/png;base64,AAAA)', start: 0, end: 31 }],
  ],
  [
    'url(data:image/svg+xml;utf8,<svg%20fill="red"/>)',
    [{ url: 'data:image/svg+xml;utf8,<svg%20fill="red"/>', fullMatch: 'url(data:image/svg+xml;utf8,<svg%20fill="red"/>)', start: 0, end: 48 }],
  ],
  // Malformed: no closing ')' before EOF -> no match.
  ['url(unclosed.png', []],
  ['url(', []],
  // Malformed: unterminated quote -> no match.
  ["url('unterminated", []],
  // The url( token match is case-insensitive.
  ['URL(UP.png)', [{ url: 'UP.png', fullMatch: 'URL(UP.png)', start: 0, end: 11 }]],
  // Multiple matches in one stylesheet keep correct offsets.
  [
    'x url(one.png) y url(two.png) z',
    [
      { url: 'one.png', fullMatch: 'url(one.png)', start: 2, end: 14 },
      { url: 'two.png', fullMatch: 'url(two.png)', start: 17, end: 29 },
    ],
  ],
  // Adjacent url() tokens split correctly.
  [
    'url(img.png)url(img2.png)',
    [
      { url: 'img.png', fullMatch: 'url(img.png)', start: 0, end: 12 },
      { url: 'img2.png', fullMatch: 'url(img2.png)', start: 12, end: 25 },
    ],
  ],
  // An unquoted value ends at the first ')' even after a backslash.
  ['url(\\).png)', [{ url: '\\', fullMatch: 'url(\\)', start: 0, end: 6 }]],
];

test('extractCssUrls parses quoted, unquoted, escaped, data:, and malformed url() tokens', () => {
  for (const [input, expected] of CASES) {
    assert.deepEqual(
      JSON.parse(JSON.stringify(extractCssUrls(input))),
      expected,
      `input ${JSON.stringify(input)}`,
    );
  }
});

test('extractCssUrls survives Function.prototype.toString() serialization into a fresh realm', () => {
  // snapshot.ts injects the parser into a browser page via
  // `globalThis.__manifestExtractCssUrls = ${extractCssUrls.toString()};`.
  // The serialized source must therefore be valid self-contained JS with no
  // references outside its own body.
  const serialized = `globalThis.__manifestExtractCssUrls = ${extractCssUrls.toString()};`;
  const sandbox = {};
  vm.runInNewContext(serialized, sandbox);
  const injected = sandbox.__manifestExtractCssUrls;
  assert.equal(typeof injected, 'function');

  for (const [input] of CASES) {
    assert.deepEqual(
      JSON.parse(JSON.stringify(injected(input))),
      JSON.parse(JSON.stringify(extractCssUrls(input))),
      `serialized copy diverged on ${JSON.stringify(input)}`,
    );
  }
});
