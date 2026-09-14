import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { access, chmod, constants, lstat, mkdir, mkdtemp, open, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve, sep } from 'node:path';

export type CheckResult = { argv: string[]; exitCode: number; stdout: { text: string; bytes: number; truncated: boolean; hash: string }; stderr: { text: string; bytes: number; truncated: boolean; hash: string } };
type Mount = { source: string; target: string; readOnly: boolean };
type Command = { executable: string; argv: string[]; cwd: string; env: Record<string, string>; timeoutMs: number; recipeArgv: string[]; mounts: Mount[]; containerName?: string };
type Execution = { exitCode: number; stdout: string; stderr: string; stdoutHash?: string; stderrHash?: string; stdoutBytes?: number; stderrBytes?: number; stdoutTruncated?: boolean; stderrTruncated?: boolean };
const PROTECTED = ['.git', '.omp', 'secrets'];
function under(root: string, path: string): boolean { const rel = relative(root, path); return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..'); }
function protectedPath(root: string, path: string, forbidden: string[]): boolean { const rel = relative(root, path); return rel === '' || [...PROTECTED, ...forbidden].some((item) => rel === item || rel.startsWith(`${item}${sep}`) || item.startsWith(`${rel}${sep}`)); }
function output(text: string, limit: number, hash?: string, bytes?: number, truncated?: boolean) { const source = Buffer.from(text); const actual = bytes ?? source.length; return { text: source.subarray(0, limit).toString(), bytes: actual, truncated: truncated ?? actual > limit, hash: hash ?? `sha256:${createHash('sha256').update(source).digest('hex')}` }; }
async function approvedExecutable(argv: string[]): Promise<{ executable: string; runtime: string; extras: { executable: string; runtime: string }[] }> {
  const requested = argv[0];
  const candidates = requested.startsWith('/') ? [requested] : ['/usr/bin', '/bin', '/opt/homebrew/bin', '/usr/local/bin'].map((root) => join(root, requested));
  let executable: string | undefined;
  for (const candidate of candidates) try { const actual = await realpath(candidate); if (['/usr/bin', '/bin', '/opt/homebrew', '/usr/local', '/Applications'].some((root) => actual === root || actual.startsWith(`${root}/`))) { executable = actual; break; } } catch {}
  if (!executable) throw new Error('approved executable is unavailable');
  const runtimeOf = (path: string) => /^\/opt\/homebrew\//.test(path) ? '/opt/homebrew' : /^\/Applications\/[^/]+\.app/.exec(path)?.[0] ?? dirname(path);
  const extras: { executable: string; runtime: string }[] = [];
  for (const value of argv.slice(1)) if (value.startsWith('/')) try { const actual = await realpath(value); await access(actual, constants.X_OK); if (['/usr/bin', '/bin', '/opt/homebrew', '/usr/local', '/Applications'].some((root) => actual.startsWith(`${root}/`))) extras.push({ executable: actual, runtime: runtimeOf(actual) }); } catch {}
  return { executable, runtime: runtimeOf(executable), extras };
}
async function provisionOutput(root: string, lexical: string): Promise<string> {
  const parent = dirname(lexical);
  const parentStat = await lstat(parent);
  if (!parentStat.isDirectory() || parentStat.isSymbolicLink() || await realpath(parent) !== parent) throw new Error('output parent is unsafe');
  try {
    const stat = await lstat(lexical);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1) throw new Error('output file is unsafe');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    const handle = await open(lexical, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
    await handle.close();
  }
  await chmod(lexical, 0o600);
  const stat = await lstat(lexical);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || (stat.mode & 0o777) !== 0o600) throw new Error('output file is unsafe');
  const actual = await realpath(lexical);
  if (actual !== lexical || !under(root, actual)) throw new Error('symlinked writes are forbidden');
  return actual;
}

async function executeDirect(command: Command, outputLimitBytes: number, signal?: AbortSignal): Promise<Execution> {
  if (signal?.aborted) throw new Error('check aborted');
  return new Promise((resolveResult, rejectResult) => {
    const child = spawn(command.executable, command.argv, { cwd: command.cwd, env: command.env, shell: false, stdio: ['ignore', 'pipe', 'pipe'], detached: true });
    const stdoutHash = createHash('sha256'); const stderrHash = createHash('sha256'); let stdout = ''; let stderr = ''; let stdoutBytes = 0; let stderrBytes = 0; let settled = false;
    const collect = (current: string, chunk: Buffer) => Buffer.concat([Buffer.from(current), chunk]).subarray(0, outputLimitBytes).toString();
    const terminate = async (reason: Error) => { if (settled) return; settled = true; clearTimeout(timer); signal?.removeEventListener('abort', aborted); try { process.kill(-child.pid!, 'SIGKILL'); } catch {} if (command.containerName) await new Promise<void>((done) => { const remover = spawn('docker', ['rm', '--force', command.containerName], { stdio: 'ignore' }); remover.once('close', () => done()); remover.once('error', () => done()); }); rejectResult(reason); };
    const aborted = () => { void terminate(new Error('check aborted')); };
    const timer = setTimeout(() => { void terminate(new Error('check timed out')); }, command.timeoutMs);
    signal?.addEventListener('abort', aborted, { once: true });
    child.stdout.on('data', (chunk: Buffer) => { stdoutHash.update(chunk); stdoutBytes += chunk.length; if (Buffer.byteLength(stdout) < outputLimitBytes) stdout = collect(stdout, chunk); });
    child.stderr.on('data', (chunk: Buffer) => { stderrHash.update(chunk); stderrBytes += chunk.length; if (Buffer.byteLength(stderr) < outputLimitBytes) stderr = collect(stderr, chunk); });
    child.once('error', (error) => { void terminate(error); });
    child.once('close', (exitCode) => { if (settled) return; settled = true; clearTimeout(timer); signal?.removeEventListener('abort', aborted); resolveResult({ exitCode: exitCode ?? 1, stdout, stderr, stdoutHash: `sha256:${stdoutHash.digest('hex')}`, stderrHash: `sha256:${stderrHash.digest('hex')}`, stdoutBytes, stderrBytes, stdoutTruncated: stdoutBytes > Buffer.byteLength(stdout), stderrTruncated: stderrBytes > Buffer.byteLength(stderr) }); });
  });
}

export async function runCheck({ repo, task, checkId, command, environment = {}, executor, backends = { 'sandbox-exec': process.platform === 'darwin', docker: true }, outputLimitBytes = 65536, signal, scratchRoot = tmpdir() }: { repo: string; task: { forbidden_policy_paths: string[]; approved_check_recipes: Record<string, unknown>[] }; checkId: string; command?: unknown; environment?: Record<string, string | undefined>; executor?: (command: Command) => Promise<Execution>; backends?: Record<string, boolean>; outputLimitBytes?: number; signal?: AbortSignal; scratchRoot?: string }): Promise<CheckResult> {
  if (signal?.aborted) throw new Error('check aborted'); if (command !== undefined) throw new Error('raw commands are not accepted');
  const recipe = task.approved_check_recipes.find((entry) => entry.id === checkId) as { id: string; argv: string[]; cwd: string; timeout_ms: number; backend: 'sandbox-exec' | 'docker'; sandbox_image?: string; write_paths: string[] } | undefined;
  if (!recipe) throw new Error('unknown approved check'); if (!Array.isArray(recipe.write_paths) || recipe.write_paths.length === 0) throw new Error('check requires declared output paths'); if (!backends[recipe.backend]) throw new Error('selected sandbox backend unavailable');
  const lexicalRepo = resolve(repo); const root = await realpath(repo); const cwd = resolve(root, recipe.cwd); if (!under(root, cwd)) throw new Error('check cwd escapes repository');
  const runtime = recipe.backend === 'sandbox-exec' ? await approvedExecutable(recipe.argv) : undefined;
  const invokedArgv = runtime ? [runtime.executable, ...recipe.argv.slice(1).map((argument) => argument.startsWith('/') && under(lexicalRepo, argument) ? join(root, relative(lexicalRepo, argument)) : argument)] : recipe.argv;
  const writable: string[] = [];
  for (const value of recipe.write_paths ?? []) { const lexical = resolve(root, value); if (!under(root, lexical) || protectedPath(root, lexical, task.forbidden_policy_paths ?? [])) throw new Error('writable protected path'); writable.push(await provisionOutput(root, lexical)); }
  const scratch = await realpath(await mkdtemp(join(scratchRoot, 'ui-delivery-check-')));
  try {
    const masks: Mount[] = [];
    if (recipe.backend === 'docker') for (const [index, forbidden] of ['.git', '.omp', 'secrets', ...(task.forbidden_policy_paths ?? [])].entries()) {
      const target = resolve(root, forbidden); if (!under(root, target)) throw new Error('forbidden path escapes repository');
      const source = join(scratch, 'masks', String(index));
      try { if ((await lstat(target)).isDirectory()) await mkdir(source, { recursive: true, mode: 0o700 }); else { await mkdir(dirname(source), { recursive: true, mode: 0o700 }); await writeFile(source, '', { mode: 0o600, flag: 'wx' }); } }
      catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; await mkdir(source, { recursive: true, mode: 0o700 }); }
      masks.push({ source, target: join('/repo', relative(root, target)), readOnly: true });
    }
    const mounts: Mount[] = [{ source: root, target: '/repo', readOnly: true }, ...writable.map((source) => ({ source, target: join('/repo', relative(root, source)), readOnly: false })), ...masks, { source: scratch, target: '/tmp/ui-delivery', readOnly: false }];
    const env: Record<string, string> = recipe.backend === 'sandbox-exec' ? { PATH: '/usr/bin:/bin:/usr/sbin:/sbin', HOME: scratch, TMPDIR: scratch } : { PATH: '/usr/bin:/bin:/usr/sbin:/sbin' };
    const containerName = `ui-delivery-${randomUUID()}`;
    const deniedReads = ['.git', '.omp', 'secrets', ...(task.forbidden_policy_paths ?? [])].map((path, index) => ['-D', `DENY_${index}=${resolve(root, path)}`] as string[]).flat();
    const extraParameters = runtime ? runtime.extras.flatMap((entry, index) => ['-D', `EXTRA_EXEC_${index}=${entry.executable}`, '-D', `EXTRA_RUNTIME_${index}=${entry.runtime}`]) : [];
    const appBundleExtra = runtime?.extras.some((entry) => entry.runtime.startsWith('/Applications/')) ?? false;
    const hostTempParameters = appBundleExtra ? ['-D', `HOST_TMP=${dirname(scratch)}`] : [];
    const spec: Command = recipe.backend === 'sandbox-exec' ? { executable: 'sandbox-exec', argv: ['-D', `REPO=${root}`, '-D', `RUNTIME=${runtime!.runtime}`, '-D', `EXEC=${runtime!.executable}`, '-D', `SCRATCH=${scratch}`, ...extraParameters, ...hostTempParameters, ...deniedReads, ...writable.flatMap((path, index) => ['-D', `WRITE_${index}=${path}`]), '-p', `(version 1) (deny default) (allow process-exec (literal (param "EXEC")) ${runtime!.extras.map((entry, index) => entry.runtime.startsWith('/Applications/') ? `(subpath (param "EXTRA_RUNTIME_${index}"))` : `(literal (param "EXTRA_EXEC_${index}"))`).join(' ')}) (allow process-fork) (allow sysctl-read) (allow mach-lookup) (allow file-read-metadata) (allow file-read* (literal "/") (literal "/dev/null") (subpath (param "REPO")) (subpath (param "RUNTIME")) ${runtime!.extras.map((_, index) => `(subpath (param "EXTRA_RUNTIME_${index}"))`).join(' ')} (subpath "/usr") (subpath "/System") (subpath "/Library")) (deny file-read* ${['.git', '.omp', 'secrets', ...(task.forbidden_policy_paths ?? [])].map((_, index) => `(subpath (param "DENY_${index}"))`).join(' ')}) (allow file-write* (literal "/dev/null") (subpath (param "SCRATCH")) ${writable.map((_, index) => `(subpath (param "WRITE_${index}"))`).join(' ')} ${appBundleExtra ? '(subpath (param "HOST_TMP"))' : ''} ) (allow network* (local unix-socket))`, '--', ...invokedArgv], cwd, env, timeoutMs: recipe.timeout_ms, recipeArgv: recipe.argv, mounts } : (() => { if (typeof recipe.sandbox_image !== 'string' || !/^[^@\s]+@sha256:[a-f0-9]{64}$/i.test(recipe.sandbox_image)) throw new Error('Docker image must be digest pinned'); return { executable: 'docker', argv: ['run', '--name', containerName, '--network', 'none', '--read-only', '--env', 'PATH=/usr/bin:/bin', ...mounts.flatMap((mount) => ['--mount', `type=bind,source=${mount.source},target=${mount.target}${mount.readOnly ? ',readonly' : ''}`]), '--workdir', `/repo/${recipe.cwd}`, recipe.sandbox_image, ...recipe.argv], cwd, env, timeoutMs: recipe.timeout_ms, recipeArgv: recipe.argv, mounts, containerName }; })();
    let execution: Execution;
    if (executor) execution = await Promise.race([executor(spec), new Promise<never>((_, reject) => { const timer = setTimeout(() => reject(new Error('check timed out')), spec.timeoutMs); signal?.addEventListener('abort', () => { clearTimeout(timer); reject(new Error('check aborted')); }, { once: true }); })]); else execution = await executeDirect(spec, outputLimitBytes, signal);
    return { argv: recipe.argv, exitCode: execution.exitCode, stdout: output(execution.stdout, outputLimitBytes, execution.stdoutHash, execution.stdoutBytes, execution.stdoutTruncated), stderr: output(execution.stderr, outputLimitBytes, execution.stderrHash, execution.stderrBytes, execution.stderrTruncated) };
  } finally { await rm(scratch, { recursive: true, force: true }); }
}
