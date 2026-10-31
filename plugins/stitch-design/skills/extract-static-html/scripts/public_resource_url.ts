/** Public destinations only. Tables follow the IANA special-purpose registries. */
import dns from 'node:dns';
import { BlockList, isIP, type LookupFunction } from 'node:net';

const private4 = new BlockList();
const translatedPrivate = new BlockList();
for (const [address, prefix] of [
  ['0.0.0.0', 8],
  ['10.0.0.0', 8],
  ['100.64.0.0', 10],
  ['127.0.0.0', 8],
  ['169.254.0.0', 16],
  ['172.16.0.0', 12],
  ['192.0.0.0', 24],
  ['192.0.2.0', 24],
  ['192.88.99.0', 24],
  ['192.168.0.0', 16],
  ['198.18.0.0', 15],
  ['198.51.100.0', 24],
  ['203.0.113.0', 24],
  ['224.0.0.0', 4],
  ['240.0.0.0', 4],
] as const) {
  private4.addSubnet(address, prefix, 'ipv4');
  translatedPrivate.addSubnet(`64:ff9b::${address}`, 96 + prefix, 'ipv6');
}
const public4Exceptions = new BlockList();
const translatedExceptions = new BlockList();
for (const address of ['192.0.0.9', '192.0.0.10']) {
  public4Exceptions.addAddress(address, 'ipv4');
  translatedExceptions.addAddress(`64:ff9b::${address}`, 'ipv6');
}
const mapped = new BlockList();
mapped.addSubnet('0.0.0.0', 0, 'ipv4');
const translated = new BlockList();
translated.addSubnet('64:ff9b::', 96, 'ipv6');
const global6 = new BlockList();
global6.addSubnet('2000::', 3, 'ipv6');
const private6 = new BlockList();
for (const [address, prefix] of [
  ['2001::', 23],
  ['2001:db8::', 32],
  ['2002::', 16],
  ['3fff::', 20],
] as const)
  private6.addSubnet(address, prefix, 'ipv6');
const public6Exceptions = new BlockList();
for (const [address, prefix] of [
  ['2001:1::1', 128],
  ['2001:1::2', 128],
  ['2001:1::3', 128],
  ['2001:3::', 32],
  ['2001:4:112::', 48],
  ['2001:20::', 28],
  ['2001:30::', 28],
] as const)
  public6Exceptions.addSubnet(address, prefix, 'ipv6');

export function isPublicAddress(address: string): boolean {
  if (address.includes('%')) return false;
  const family = isIP(address);
  if (!family) return false;
  const type = family === 4 ? 'ipv4' : 'ipv6';
  if (mapped.check(address, type))
    return public4Exceptions.check(address, type) || !private4.check(address, type);
  if (translated.check(address, 'ipv6'))
    return translatedExceptions.check(address, 'ipv6') || !translatedPrivate.check(address, 'ipv6');
  return (
    global6.check(address, 'ipv6') &&
    (!private6.check(address, 'ipv6') || public6Exceptions.check(address, 'ipv6'))
  );
}

export function isAllowedResourceUrl(url: URL): boolean {
  if (!['http:', 'https:'].includes(url.protocol)) return false;
  const host = url.hostname.replace(/^\[|\]$/g, '').toLowerCase();
  const name = host.replace(/\.$/, '');
  if (name === 'localhost' || name.endsWith('.localhost')) return false;
  return isIP(host) ? isPublicAddress(host) : !host.includes(':') && !host.includes('%');
}

/** Resolve once inside the request deadline; the socket receives only this validated snapshot. */
export function publicLookup(active: () => boolean): LookupFunction {
  return (hostname, options, callback) => {
    dns.lookup(hostname, { all: true, verbatim: true }, (error, answers) => {
      if (!active()) return;
      if (error) {
        callback(error, '', 0);
        return;
      }
      if (
        !answers.length ||
        answers.some(({ address, family }) => isIP(address) !== family || !isPublicAddress(address))
      ) {
        callback(new Error('Blocked resource DNS destination'), '', 0);
        return;
      }
      const selected = answers
        .filter((answer) => !options.family || answer.family === options.family)
        .map((answer) => ({ address: answer.address, family: answer.family }));
      if (!selected.length) {
        callback(new Error('No public resource address'), '', 0);
        return;
      }
      if (options.all) callback(null, selected);
      else callback(null, selected[0].address, selected[0].family);
    });
  };
}
