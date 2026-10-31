/** Invocation-wide response/cache/output budgets. No URL policy lives here. */
import http from 'node:http';
import https from 'node:https';

export const DEFAULT_LIMITS = Object.freeze({
  resourceBytes: 8 * 1024 * 1024,
  downloadBytes: 32 * 1024 * 1024,
  encodedBytes: 48 * 1024 * 1024,
  pageBytes: 64 * 1024 * 1024,
  outputBytes: 128 * 1024 * 1024,
  requests: 256,
  references: 10000,
  urlBytes: 8192,
});
export type Limits = { [Key in keyof typeof DEFAULT_LIMITS]: number };
export const FALLBACK =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

export class ResourceBudget {
  readonly limits: Limits;
  downloaded = 0;
  encoded = 0;
  output = 0;
  requests = 0;
  entries = 0;
  closed = false;
  readonly aborters = new Set<() => void>();

  constructor(limits: Partial<Limits> = {}) {
    this.limits = { ...DEFAULT_LIMITS, ...limits };
    for (const value of Object.values(this.limits)) {
      if (!Number.isSafeInteger(value) || value <= 0) throw new Error('Invalid resource limit');
    }
  }

  exhaust(): never {
    this.closed = true;
    for (const abort of [...this.aborters]) abort();
    throw new Error('Aggregate resource budget exceeded');
  }

  reserve(kind: 'requests' | 'entries'): void {
    if (this.closed || this[kind] >= this.limits.requests) this.exhaust();
    this[kind]++;
  }

  consume(bytes: number): void {
    if (this.closed || bytes > this.limits.downloadBytes - this.downloaded) this.exhaust();
    this.downloaded += bytes;
  }

  encode(bytes: number): void {
    if (this.closed || bytes > this.limits.encodedBytes - this.encoded) this.exhaust();
    this.encoded += bytes;
  }

  get remainingOutput(): number {
    return Math.min(this.limits.pageBytes, this.limits.outputBytes - this.output);
  }
}

type Response = { redirect: string } | { bytes: Buffer; contentType: string };

function collect(url: URL, budget: ResourceBudget, deadline: number): Promise<Response> {
  budget.reserve('requests');
  return new Promise((resolve, reject) => {
    let response: http.IncomingMessage | undefined;
    let request: http.ClientRequest | undefined;
    let settled = false;
    let length = 0;
    let blocks: Buffer[] = [];
    const finish = (error?: Error, result?: Response) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      budget.aborters.delete(abort);
      blocks = [];
      response?.destroy();
      request?.destroy();
      if (error) reject(error);
      else resolve(result!);
    };
    const abort = () => finish(new Error('Resource request cancelled'));
    const timer = setTimeout(
      () => finish(new Error('Resource deadline exceeded')),
      Math.max(1, deadline - Date.now()),
    );
    budget.aborters.add(abort);
    if (deadline <= Date.now()) {
      abort();
      return;
    }
    try {
      request = (url.protocol === 'https:' ? https : http).get(
        url,
        {
          headers: { 'User-Agent': 'Mozilla/5.0 (compatible; SnapshotBot/2.0)' },
          timeout: Math.max(1, deadline - Date.now()),
        },
        (resp) => {
          response = resp;
          resp.on('error', (error) => finish(error));
          resp.on('aborted', abort);
          resp.on('close', () => {
            if (!settled) finish(new Error('Incomplete resource response'));
          });
          if (resp.statusCode! >= 300 && resp.statusCode! < 400 && resp.headers.location) {
            try {
              finish(undefined, { redirect: new URL(resp.headers.location, url).href });
            } catch {
              finish(new Error('Invalid redirect URL'));
            }
            return;
          }
          if (resp.statusCode! >= 400) {
            finish(new Error(`HTTP ${resp.statusCode}`));
            return;
          }
          const declared = resp.headers['content-length'];
          if (
            declared !== undefined &&
            (!/^\d+$/.test(declared) ||
              Number(declared) >
                Math.min(
                  budget.limits.resourceBytes,
                  budget.limits.downloadBytes - budget.downloaded,
                ))
          ) {
            finish(new Error('Declared resource size exceeds budget'));
            return;
          }
          resp.on('data', (chunk: Buffer) => {
            if (settled) return;
            try {
              budget.consume(chunk.length);
              if (chunk.length > budget.limits.resourceBytes - length)
                throw new Error('Resource size limit exceeded');
              let offset = 0;
              while (offset < chunk.length) {
                const position = length % 65536;
                if (position === 0)
                  blocks.push(
                    Buffer.allocUnsafe(Math.min(65536, budget.limits.resourceBytes - length)),
                  );
                const block = blocks[blocks.length - 1];
                const copied = chunk.copy(
                  block,
                  position,
                  offset,
                  offset + block.length - position,
                );
                offset += copied;
                length += copied;
              }
            } catch (error) {
              finish(error instanceof Error ? error : new Error('Resource collection failed'));
            }
          });
          resp.on('end', () => {
            if (settled) return;
            finish(undefined, {
              bytes: Buffer.concat(blocks, length),
              contentType: resp.headers['content-type'] || 'image/jpeg',
            });
          });
        },
      );
      request.on('error', (error) => finish(error));
      request.on('timeout', abort);
    } catch (error) {
      finish(error instanceof Error ? error : new Error('Resource request failed'));
    }
  });
}

export async function fetchResource(
  url: string,
  options: {
    budget: ResourceBudget;
    timeout: number;
    isSafeUrl: (url: URL) => boolean;
  },
): Promise<string> {
  const { budget, timeout, isSafeUrl } = options;
  const deadline = Date.now() + timeout;
  const visited = new Set<string>();
  for (let hop = 0; hop < 5; hop++) {
    if (Buffer.byteLength(url) > budget.limits.urlBytes || visited.has(url))
      throw new Error('Resource redirect limit exceeded');
    visited.add(url);
    const parsed = new URL(url);
    if (!isSafeUrl(parsed)) throw new Error('Blocked resource URL');
    const result = await collect(parsed, budget, deadline);
    if ('redirect' in result) {
      url = result.redirect;
      continue;
    }
    const prefix = `data:${result.contentType};base64,`;
    budget.encode(Buffer.byteLength(prefix) + 4 * Math.ceil(result.bytes.length / 3));
    return prefix + result.bytes.toString('base64');
  }
  throw new Error('Resource redirect limit exceeded');
}
