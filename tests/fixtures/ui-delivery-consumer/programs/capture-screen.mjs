import { lstat, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [chromePath, targetPath, pngPath, resultPath] = process.argv.slice(2);
if (![chromePath, targetPath, pngPath, resultPath].every(Boolean)) throw new Error('usage: capture-screen.mjs CHROME TARGET PNG RESULT');
const resolvedTarget = resolve(targetPath);
const resolvedPng = resolve(pngPath);
const resolvedResult = resolve(resultPath);
const emit = (passed) => writeFile(resolvedResult, `${JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: passed ? 1 : 0, failed: passed ? 0 : 1, skipped: 0 })}\n`, 'utf8');
const homeDirectory = process.env.HOME ?? '/tmp/ui-delivery';
const userDataDir = `${homeDirectory}/chrome-profile`;
const crashDumpsDir = `${homeDirectory}/crash-dumps`;
const sanitizeDiagnostic = (value) => value.replace(/file:\/\/\S+/g, '[approved local target]').replace(/https?:\/\/\S+/g, '[url]').replace(/\s+/g, ' ').trim().slice(0, 4096);
const launch = () => new Promise((resolveLaunch, rejectLaunch) => {
  let stderr = '';
  const child = spawn(resolve(chromePath), [
    '--headless=new', '--disable-gpu', '--disable-javascript', '--no-first-run', '--disable-background-networking',
    '--disable-dev-shm-usage', '--disable-breakpad', '--disable-crash-reporter', '--noerrdialogs',
    `--user-data-dir=${userDataDir}`, `--crash-dumps-dir=${crashDumpsDir}`,
    '--hide-scrollbars', '--window-size=1280,900', `--screenshot=${resolvedPng}`, pathToFileURL(resolvedTarget).href,
  ], { shell: false, stdio: ['ignore', 'ignore', 'pipe'] });
  child.stderr.on('data', (chunk) => { if (Buffer.byteLength(stderr) < 4096) stderr += Buffer.from(chunk).subarray(0, 4096 - Buffer.byteLength(stderr)).toString(); });
  child.once('error', rejectLaunch);
  child.once('close', (code) => {
    const detail = sanitizeDiagnostic(stderr);
    code === 0 ? resolveLaunch() : rejectLaunch(new Error(`Chrome exited ${code}${detail ? `: ${detail}` : ''}`));
  });
});

try {
  await Promise.all([mkdir(userDataDir, { recursive: true, mode: 0o700 }), mkdir(crashDumpsDir, { recursive: true, mode: 0o700 })]);
  await rm(resolvedPng, { force: true });
  await launch();
  const stat = await lstat(resolvedPng);
  const bytes = await readFile(resolvedPng);
  const png = bytes.length > 8 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  if (!stat.isFile() || stat.isSymbolicLink() || !png) throw new Error('capture is not a PNG');
  await emit(true);
} catch (error) {
  const message = error instanceof Error ? error.message : 'capture failed';
  process.stderr.write(`${`capture failed: ${message}`.slice(0, 4096)}\n`);
  await emit(false);
  process.exitCode = 1;
}
