import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { realpath } from 'node:fs/promises';
import { join, relative, resolve, sep } from 'node:path';

type Command = { executable: string; argv: string[]; cwd: string; env: Record<string, string>; timeoutMs: number; recipeArgv: string[]; mounts: { source: string; target: string; readOnly: boolean }[] };
type Output = { text: string; bytes: number; truncated: boolean; hash: string };

function under(root: string, path: string): boolean {
  const rel = relative(root, path);
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..');
}

function bound(value: string, limit: number): Output {
  const bytes = Buffer.byteLength(value);
  return { text: Buffer.from(value).subarray(0, limit).toString(), bytes: Math.min(bytes, limit), truncated: bytes > limit, hash: `sha256:${createHash('sha256').update(value).digest('hex')}` };
}

async function executeDirect(command: Command): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  return new Promise((resolveResult, reject) => {
    const child = spawn(command.executable, command.argv, { cwd: command.cwd, env: command.env, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = ''; let stderr = ''; let timedOut = false;
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    const timer = setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, command.timeoutMs);
    child.on('error', (error) => { clearTimeout(timer); reject(error); });
    child.on('close', (exitCode) => {
      clearTimeout(timer);
      if (timedOut) reject(new Error('check timed out'));
      else resolveResult({ exitCode: exitCode ?? 1, stdout, stderr });
    });
  });
}

export async function runCheck({ repo, task, checkId, command, environment = {}, executor = executeDirect, backends = { 'sandbox-exec': process.platform === 'darwin', docker: true }, outputLimitBytes = 65536 }: { repo: string; task: any; checkId: string; command?: unknown; environment?: Record<string, string | undefined>; executor?: (command: Command) => Promise<{ exitCode: number; stdout: string; stderr: string }>; backends?: Record<string, boolean>; outputLimitBytes?: number }) {
  if (command !== undefined) throw new Error('raw commands are not accepted');
  const recipe = task.approved_check_recipes?.find((entry: any) => entry.id === checkId);
  if (!recipe) throw new Error('unknown approved check');
  if (!backends[recipe.backend]) throw new Error('selected sandbox backend unavailable');
  const root = await realpath(repo);
  const cwd = resolve(root, recipe.cwd);
  if (!under(root, cwd)) throw new Error('check cwd escapes repository');
  const env = Object.fromEntries((recipe.env ?? []).filter((name: string) => typeof environment[name] === 'string').map((name: string) => [name, environment[name]!])) as Record<string, string>;
  const mounts = [{ source: root, target: '/repo', readOnly: true }, { source: cwd, target: '/repo/work', readOnly: false }];
  let executable: string;
  let argv: string[];
  if (recipe.backend === 'sandbox-exec') {
    executable = 'sandbox-exec';
    const profile = `(version 1) (deny default) (allow process*) (allow file-read* (subpath "${root}")) (allow file-write* (subpath "${cwd}"))`;
    argv = ['-p', profile, '--', ...recipe.argv];
  } else {
    if (typeof recipe.sandbox_image !== 'string' || !/@sha256:[a-f0-9]{16,}$/i.test(recipe.sandbox_image)) throw new Error('Docker image must be digest pinned');
    executable = 'docker';
    argv = ['run', '--rm', '--network', 'none', '--read-only', '--mount', `type=bind,source=${root},target=/repo,readonly`, '--mount', `type=bind,source=${cwd},target=/repo/work`, '--workdir', '/repo/work', recipe.sandbox_image, ...recipe.argv];
  }
  const result = await executor({ executable, argv, cwd, env, timeoutMs: recipe.timeout_ms, recipeArgv: recipe.argv, mounts });
  return { checkId, argv: recipe.argv, exitCode: result.exitCode, stdout: bound(result.stdout, outputLimitBytes), stderr: bound(result.stderr, outputLimitBytes) };
}
