/** Bounded asset embedding shared by every output page in one invocation. */
import { extractCssUrls } from './css_url_parser.ts';
import { ResourceBudget, fetchResource, FALLBACK } from './bounded_resources.ts';

type Reference = { start: number; end: number; url: string; prefix: string; suffix: string };

export class ResourceEmbedder {
  readonly budget: ResourceBudget;
  readonly cache = new Map<string, Promise<string>>();
  readonly isSafeUrl: (url: URL) => boolean;
  readonly isImageUrl: (url: string) => boolean;

  constructor(options: {
    isSafeUrl: (url: URL) => boolean;
    isImageUrl: (url: string) => boolean;
    budget?: ResourceBudget;
  }) {
    this.budget = options.budget ?? new ResourceBudget();
    this.isSafeUrl = options.isSafeUrl;
    this.isImageUrl = options.isImageUrl;
  }

  private fetch(url: string, timeout: number): Promise<string> {
    const cached = this.cache.get(url);
    if (cached) return cached;
    try {
      if (Buffer.byteLength(url) > this.budget.limits.urlBytes)
        throw new Error('Resource URL too long');
      this.budget.reserve('entries');
    } catch {
      return Promise.resolve(FALLBACK);
    }
    const pending = fetchResource(url, {
      budget: this.budget,
      timeout,
      isSafeUrl: this.isSafeUrl,
    }).catch((error) => {
      console.warn(
        `  WARN: ${String(error.message)
          .slice(0, 160)
          .replace(/[\r\n]/g, ' ')}; using resource placeholder`,
      );
      return FALLBACK;
    });
    this.cache.set(url, pending);
    return pending;
  }

  private references(html: string): Reference[] {
    const refs: Reference[] = [];
    const add = (ref: Reference) => {
      if (!this.isImageUrl(ref.url)) return;
      if (refs.length >= this.budget.limits.references)
        throw new Error('Page resource-reference limit exceeded');
      refs.push(ref);
    };
    for (const match of html.matchAll(/(src|poster)="(https?:\/\/[^"]+)"/g)) {
      add({
        start: match.index,
        end: match.index + match[0].length,
        url: match[2],
        prefix: `${match[1]}="`,
        suffix: '"',
      });
    }
    let cssTokens = 0;
    for (const _match of html.matchAll(/url\(/gi)) {
      if (++cssTokens > this.budget.limits.references)
        throw new Error('CSS resource-reference limit exceeded');
    }
    for (const ref of extractCssUrls(html)) {
      if (/^https?:\/\//.test(ref.url)) add({ ...ref, prefix: "url('", suffix: "')" });
    }
    let end = 0;
    return refs
      .sort((a, b) => a.start - b.start)
      .filter((ref) => {
        if (ref.start < end) return false;
        end = ref.end;
        return true;
      });
  }

  async embed(html: string, concurrency: number, timeout: number): Promise<string> {
    const limit = this.budget.remainingOutput;
    let size = Buffer.byteLength(html);
    if (size > limit) throw new Error('HTML output size limit exceeded');
    const refs = this.references(html);
    const urls = [...new Set(refs.map((ref) => ref.url))];
    let next = 0;
    await Promise.all(
      Array.from({ length: Math.min(concurrency, urls.length) }, async () => {
        while (next < urls.length) await this.fetch(urls[next++], timeout);
      }),
    );
    const replacements: Array<{ ref: Reference; value: string }> = [];
    const encodedSizes = new Map<string, number>();
    for (const ref of refs) {
      const value = await this.fetch(ref.url, timeout);
      if (!encodedSizes.has(ref.url)) encodedSizes.set(ref.url, Buffer.byteLength(value));
      size +=
        Buffer.byteLength(ref.prefix) +
        encodedSizes.get(ref.url)! +
        Buffer.byteLength(ref.suffix) -
        Buffer.byteLength(html.slice(ref.start, ref.end));
      replacements.push({ ref, value });
    }
    if (size > limit) throw new Error('HTML output size limit exceeded');
    const pieces: string[] = [];
    let position = 0;
    for (const { ref, value } of replacements) {
      pieces.push(html.slice(position, ref.start), ref.prefix, value, ref.suffix);
      position = ref.end;
    }
    pieces.push(html.slice(position));
    this.budget.output += size;
    return pieces.join('');
  }
}
