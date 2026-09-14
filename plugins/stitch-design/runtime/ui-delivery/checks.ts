import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, relative, resolve, sep } from 'node:path';

type Mount = { source: string; target: string; readOnly: boolean };
type Command = { executable: string; argv: string[]; cwd: string; env: Record<string, string>; timeoutMs: number; recipeArgv: string[]; mounts: Mount[] };
type Output = { text: string; bytes: number; truncated: boolean; hash: string };
type Execution = { exitCode: number; stdout: string; stderr: string; stdoutHash?: string; stderrHash?: string; stdoutBytes?: number; stderrBytes?: number; stdoutTruncated?: boolean; stderrTruncated?: boolean };

function under(root: string, path: string): boolean {
  const rel = relative(root, path);
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..');
}

function bound(value: string, limit: number): Output {
  const bytes = Buffer.byteLength(value);
  return { text: Buffer.from(value).subarray(0, limit).toString(), bytes: Math.min(bytes, limit), truncated: bytes > limit, hash: `sha256:${createHash('sha256').update(value).digest('hex')}` };
}

function streamed(text: string, hash: string, bytes: number, truncated: boolean): Output {
  return { text, hash, bytes: Math.min(bytes, Buffer.byteLength(text)), truncated };
}

async function executeDirect(command: Command, outputLimitBytes = 65536): Promise<Execution> {
  const { promise, resolve: finish, reject } = Promise.withResolvers<Execution>();
  const child = spawn(command.executable, command.argv, { cwd: command.cwd, env: command.env, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
  const stdout = createHash('sha256'); const stderr = createHash('sha256');
  let stdoutText = ''; let stderrText = ''; let stdoutBytes = 0; let stderrBytes = 0; let timedOut = false;
  const collect = (chunk: Buffer, hash: ReturnType<typeof createHash>, current: string): string => {
    hash.update(chunk);
    if (Buffer.byteLength(current) >= outputLimitBytes) return current;
    return Buffer.concat([Buffer.from(current), chunk]).subarray(0, outputLimitBytes).toString();
  };
  child.stdout.on('data', (chunk: Buffer) => { stdoutBytes += chunk.length; stdoutText = collect(chunk, stdout, stdoutText); });
  child.stderr.on('data', (chunk: Buffer) => { stderrBytes += chunk.length; stderrText = collect(chunk, stderr, stderrText); });
  const timer = setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, command.timeoutMs);
  child.on('error', (error) => { clearTimeout(timer); reject(error); });
  child.on('close', (exitCode) => {
    clearTimeout(timer);
    if (timedOut) reject(new Error('check timed out'));
    else finish({ exitCode: exitCode ?? 1, stdout: stdoutText, stderr: stderrText, stdoutHash: `sha256:${stdout.digest('hex')}`, stderrHash: `sha256:${stderr.digest('hex')}`, stdoutBytes, stderrBytes, stdoutTruncated: stdoutBytes > Buffer.byteLength(stdoutText), stderrTruncated: stderrBytes > Buffer.byteLength(stderrText) });
  });
  return promise;
}

export async function runCheck({ repo, task, checkId, command, environment = {}, executor, backends = { 'sandbox-exec': process.platform === 'darwin', docker: true }, outputLimitBytes = 65536 }: { repo: string; task: { allowed_paths: string[]; approved_check_recipes: Record<string, unknown>[] }; checkId: string; command?: unknown; environment?: Record<string, string | undefined>; executor?: (command: Command) => Promise<Execution>; backends?: Record<string, boolean>; outputLimitBytes?: number }) {
  if (command !== undefined) throw new Error('raw commands are not accepted');
  const recipe = task.approved_check_recipes.find((entry) => entry.id === checkId) as { id: string; argv: string[]; cwd: string; timeout_ms: number; backend: 'sandbox-exec' | 'docker'; sandbox_image?: string; env?: string[] } | undefined;
  if (!recipe) throw new Error('unknown approved check');
  if (!backends[recipe.backend]) throw new Error('selected sandbox backend unavailable');
  const root = await realpath(repo);
  const cwd = resolve(root, recipe.cwd);
  if (!under(root, cwd)) throw new Error('check cwd escapes repository');
  const writable = await Promise.all(task.allowed_paths.map(async (path) => {
    const allowed = resolve(root, path);
    if (!under(root, allowed)) throw new Error('allowed path escapes repository');
    return realpath(allowed);
  }));
  if (!writable.some((path) => under(path, cwd))) throw new Error('check cwd is not an approved writable path');
  const scratch = await mkdtemp(join(tmpdir(), 'ui-delivery-check-'));
  const env = Object.fromEntries((recipe.env ?? []).filter((name) => typeof environment[name] === 'string').map((name) => [name, environment[name]!])) as Record<string, string>;
  const mounts: Mount[] = [{ source: root, target: '/repo', readOnly: true }, ...writable.map((source) => ({ source, target: join('/repo', relative(root, source)), readOnly: false })), { source: scratch, target: '/tmp/ui-delivery', readOnly: false }];
  const commandSpec: Command = recipe.backend === 'sandbox-exec'
    ? { executable: 'sandbox-exec', argv: ['-p', `(version 1) (deny default) (allow process*) (allow file-read* (subpath "${root}")) ${writable.map((path) => `(allow file-write* (subpath "${path}"))`).join(' ')} (allow file-write* (subpath "${scratch}"))`, '--', ...recipe.argv], cwd, env, timeoutMs: recipe.timeout_ms, recipeArgv: recipe.argv, mounts }
    : (() => {
        if (typeof recipe.sandbox_image !== 'string' || !/^[^@\s]+@sha256:[a-f0-9]{16,}$/i.test(recipe.sandbox_image)) throw new Error('Docker image must be digest pinned');
        return { executable: 'docker', argv: ['run', '--rm', '--network', 'none', '--read-only', ...mounts.flatMap((mount) => ['--mount', `type=bind,source=${mount.source},target=${mount.target}${mount.readOnly ? ',readonly' : ''}`]), '--workdir', `/repo/${recipe.cwd}`, recipe.sandbox_image, ...recipe.argv], cwd, env, timeoutMs: recipe.timeout_ms, recipeArgv: recipe.argv, mounts };
      })();
  const execution = executor ? await executor(commandSpec) : await executeDirect(commandSpec, outputLimitBytes);
  const stdout = execution.stdoutHash ? streamed(execution.stdout, execution.stdoutHash, execution.stdoutBytes ?? Buffer.byteLength(execution.stdout), execution.stdoutTruncated ?? false) : bound(execution.stdout, outputLimitBytes);
  const stderr = execution.stderrHash ? streamed(execution.stderr, execution.stderrHash, execution.stderrBytes ?? Buffer.byteLength(execution.stderr), execution.stderrTruncated ?? false) : bound(execution.stderr, outputLimitBytes);
  return { checkId, argv: recipe.argv, exitCode: execution.exitCode, stdout, stderr };
}
