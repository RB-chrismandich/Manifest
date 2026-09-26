/**
 * css_url_parser.ts — Shared robust CSS url() parser.
 *
 * Single source of truth for the character-by-character url() scanner used by
 * extract_inline_html.ts, post_process.ts, and snapshot.ts. snapshot.ts
 * serializes extractCssUrls into the browser page via
 * Function.prototype.toString(), so the function body MUST stay
 * self-contained: no imports, no helpers, no closures over module state.
 */

export interface CssUrlRef {
  url: string;
  fullMatch: string;
  start: number;
  end: number;
}

export function extractCssUrls(text: string): CssUrlRef[] {
  const results: CssUrlRef[] = [];
  let i = 0;
  const len = text.length;

  while (i < len) {
    // Look for 'url(' — case insensitive
    if (
      i + 3 < len &&
      text[i].toLowerCase() === 'u' &&
      text[i + 1].toLowerCase() === 'r' &&
      text[i + 2].toLowerCase() === 'l' &&
      text[i + 3] === '('
    ) {
      const urlStart = i;
      i += 4;

      // Skip whitespace
      while (i < len && (text[i] === ' ' || text[i] === '\t' || text[i] === '\n' || text[i] === '\r')) i++;

      // Check for quote
      let quote: string | null = null;
      if (i < len && (text[i] === '"' || text[i] === "'")) {
        quote = text[i];
        i++;
      }

      // Read the URL value
      let url = '';
      if (quote) {
        while (i < len && text[i] !== quote) {
          if (text[i] === '\\' && i + 1 < len) {
            i++;
            url += text[i];
          } else {
            url += text[i];
          }
          i++;
        }
        if (i < len) i++; // closing quote
      } else {
        while (i < len && text[i] !== ')' && text[i] !== ' ' && text[i] !== '\t' && text[i] !== '\n') {
          url += text[i];
          i++;
        }
      }

      // Skip trailing whitespace before ')'
      while (i < len && (text[i] === ' ' || text[i] === '\t' || text[i] === '\n' || text[i] === '\r')) i++;

      if (i < len && text[i] === ')') {
        const fullMatch = text.substring(urlStart, i + 1);
        results.push({ url: url.trim(), fullMatch, start: urlStart, end: i + 1 });
        i++;
      } else {
        i = urlStart + 1;
      }
    } else {
      i++;
    }
  }

  return results;
}
