import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const [contractPath, targetPath] = process.argv.slice(2);
if (![contractPath, targetPath].every(Boolean)) throw new Error('usage: check-design.mjs CONTRACT TARGET');

const exactText = (source, tag, expected) => new RegExp(`<${tag}\\b[^>]*>\\s*${expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*</${tag}>`, 'i').test(source);
const classPresent = (source, expected) => new RegExp(`class=["'][^"']*\\b${expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b[^"']*["']`, 'i').test(source);
const emit = (passed) => {
  process.stdout.write(`${JSON.stringify({
    schema: 'ui-delivery-verifier-output-v1',
    result: { schema: 'ui-delivery-check-v1', required: 1, passed: passed ? 1 : 0, failed: passed ? 0 : 1, skipped: 0 },
    artifacts: [],
  })}\n`);
  if (!passed) process.exitCode = 1;
};

try {
  const contract = JSON.parse(await readFile(resolve(contractPath), 'utf8'));
  const source = await readFile(resolve(targetPath), 'utf8');
  const requirements = contract.requirements;
  const normalized = source.replace(/\s+/g, ' ').toLowerCase();
  const passed =
    /^\s*<!doctype html>/i.test(source) &&
    /<html\b/i.test(source) && /<head\b/i.test(source) && /<body\b/i.test(source) && /<main\b/i.test(source) &&
    exactText(source, 'title', requirements.title) &&
    exactText(source, 'h1', requirements.heading) &&
    source.includes(requirements.summary) &&
    classPresent(source, requirements.layout_class) &&
    normalized.includes(requirements.layout_css.toLowerCase());
  if (!passed) emit(false);
  else emit(true);
} catch {
  emit(false);
}
