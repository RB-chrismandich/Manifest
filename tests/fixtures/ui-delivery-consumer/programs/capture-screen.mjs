import { lstat, readFile, rm, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [chromePath, targetPath, pngPath, resultPath] = process.argv.slice(2);
if (![chromePath, targetPath, pngPath, resultPath].every(Boolean)) throw new Error('usage: capture-screen.mjs CHROME TARGET PNG RESULT');
const resolvedTarget = resolve(targetPath);
const resolvedPng = resolve(pngPath);
const resolvedResult = resolve(resultPath);
const emit = (passed) => writeFile(resolvedResult, `${JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: passed ? 1 : 0, failed: passed ? 0 : 1, skipped: 0 })}\n`, 'utf8');
const launch = () => new Promise((resolveLaunch, rejectLaunch) => {
  const child = spawn(resolve(chromePath), [
    '--headless=new', '--disable-gpu', '--no-first-run', '--disable-background-networking',
    '--hide-scrollbars', '--window-size=1280,900', `--screenshot=${resolvedPng}`, pathToFileURL(resolvedTarget).href,
  ], { shell: false, stdio: 'ignore' });
  child.once('error', rejectLaunch);
  child.once('close', (code) => code === 0 ? resolveLaunch() : rejectLaunch(new Error(`Chrome exited ${code}`)));
});

try {
  await rm(resolvedPng, { force: true });
  await launch();
  const stat = await lstat(resolvedPng);
  const bytes = await readFile(resolvedPng);
  const png = bytes.length > 8 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  if (!stat.isFile() || stat.isSymbolicLink() || !png) throw new Error('capture is not a PNG');
  await emit(true);
} catch {
  await emit(false);
  process.exitCode = 1;
}
