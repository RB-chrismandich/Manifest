import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { chmod, constants, lstat, mkdir, mkdtemp, open, readFile, realpath, rm, unlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve, sep } from 'node:path';

export type CheckResult = { argv: string[]; exitCode: number; stdout: { text: string; bytes: number; truncated: boolean; hash: string }; stderr: { text: string; bytes: number; truncated: boolean; hash: string } };
type Mount = { source: string; target: string; readOnly: boolean };
type Command = { executable: string; argv: string[]; cwd: string; env: Record<string, string>; timeoutMs: number; recipeArgv: string[]; mounts: Mount[]; containerName?: string };
type Execution = { exitCode: number; stdout: string; stderr: string; stdoutHash?: string; stderrHash?: string; stdoutBytes?: number; stderrBytes?: number; stdoutTruncated?: boolean; stderrTruncated?: boolean };
const PROTECTED = ['.git', '.omp', 'secrets'];
function under(root: string, path: string): boolean { const rel = relative(root, path); return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..'); }
function protectedPath(root: string, path: string, forbidden: string[]): boolean { const rel = relative(root, path); return rel === '' || [...PROTECTED, ...forbidden].some((item) => rel === item || rel.startsWith(`${item}${sep}`) || item.startsWith(`${rel}${sep}`)); }
function strictlyUnder(root: string, path: string): boolean { return root !== path && under(root, path); }
function output(text: string, limit: number, hash?: string, bytes?: number, truncated?: boolean) { const source = Buffer.from(text); const actual = bytes ?? source.length; return { text: source.subarray(0, limit).toString(), bytes: actual, truncated: truncated ?? actual > limit, hash: hash ?? `sha256:${createHash('sha256').update(source).digest('hex')}` }; }

const VERIFIER_ENVELOPE_LIMIT = 4 * 1024 * 1024;
type VerifierEnvelope = { schema: 'ui-delivery-verifier-output-v1'; result: Record<string, unknown>; artifacts: Array<{ path: string; encoding: 'base64'; data: string }> };
function safeDockerMountPath(path: string): void {
  if (!path || /[,\r\n=]/.test(path)) throw new Error('unsafe Docker mount path');
}
function verifierEnvelope(stdout: string, writePaths: string[], resultPath: string): VerifierEnvelope {
  if (Buffer.byteLength(stdout) > VERIFIER_ENVELOPE_LIMIT) throw new Error('verifier output exceeds protocol limit');
  const lines = stdout.split('\n').filter(Boolean);
  if (lines.length !== 1) throw new Error('verifier output must be one envelope');
  let value: unknown;
  try { value = JSON.parse(lines[0]); } catch { throw new Error('verifier output is malformed'); }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('verifier output is malformed');
  const envelope = value as Partial<VerifierEnvelope>;
  if (envelope.schema !== 'ui-delivery-verifier-output-v1' || !envelope.result || typeof envelope.result !== 'object' || Array.isArray(envelope.result) || !Array.isArray(envelope.artifacts) || !writePaths.includes(resultPath)) throw new Error('verifier output is malformed');
  const seen = new Set<string>([resultPath]);
  let artifactBytes = 0;
  for (const artifact of envelope.artifacts) {
    if (!artifact || typeof artifact !== 'object' || typeof artifact.path !== 'string' || typeof artifact.data !== 'string' || artifact.encoding !== 'base64' || !writePaths.includes(artifact.path) || seen.has(artifact.path)) throw new Error('verifier artifact is malformed');
    const bytes = Buffer.from(artifact.data, 'base64');
    if (bytes.toString('base64') !== artifact.data) throw new Error('verifier artifact is malformed');
    artifactBytes += bytes.length;
    if (artifactBytes > VERIFIER_ENVELOPE_LIMIT) throw new Error('verifier artifacts exceed protocol limit');
    seen.add(artifact.path);
  }
  return envelope as VerifierEnvelope;
}
async function persistVerifierOutputs(root: string, envelope: VerifierEnvelope, outputs: Map<string, string>, resultPath: string): Promise<void> {
  const result = outputs.get(resultPath);
  if (!result) throw new Error('verifier result path is unavailable');
  await writeFile(result, `${JSON.stringify(envelope.result)}\n`, { mode: 0o600, flag: 'w' });
  for (const artifact of envelope.artifacts) {
    const target = outputs.get(artifact.path);
    if (!target) throw new Error('verifier artifact path is unavailable');
    await writeFile(target, Buffer.from(artifact.data, 'base64'), { mode: 0o600, flag: 'w' });
  }
}
const APPROVED_DOCKER_RUNTIME_BASENAMES: Record<string, true> = { node: true, python3: true };
function approvedDockerRuntime(argv: string[]): void {
  if (!APPROVED_DOCKER_RUNTIME_BASENAMES[argv[0]]) throw new Error('approved Docker runtime is unavailable');
}
async function validateOutputParent(root: string, lexical: string): Promise<void> {
  const parent = dirname(lexical);
  const parentStat = await lstat(parent);
  if (!parentStat.isDirectory() || parentStat.isSymbolicLink() || await realpath(parent) !== parent) throw new Error('output parent is unsafe');
}
async function provisionOutput(root: string, lexical: string): Promise<string> {
  await validateOutputParent(root, lexical);
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

type OutputLock = { path: string; owner: string; dev: number; ino: number; ownerWritten: boolean };
async function releaseOutputLocks(locks: OutputLock[]): Promise<void> {
  for (const lock of [...locks].reverse()) try {
    const [contents, stat] = await Promise.all([readFile(lock.path, 'utf8'), lstat(lock.path)]);
    if (stat.isFile() && !stat.isSymbolicLink() && stat.nlink === 1 && (lock.ownerWritten ? contents === lock.owner : stat.dev === lock.dev && stat.ino === lock.ino)) await unlink(lock.path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
}
async function acquireOutputLocks(outputs: string[]): Promise<OutputLock[]> {
  const locks: OutputLock[] = [];
  try {
    for (const outputPath of [...new Set(outputs)].sort()) {
      const path = `${outputPath}.ui-delivery.lock`;
      const owner = randomUUID();
      let handle;
      try {
        handle = await open(path, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'EEXIST') throw new Error('check output is busy');
        throw error;
      }
      const stat = await handle.stat();
      const lock = { path, owner, dev: stat.dev, ino: stat.ino, ownerWritten: false };
      locks.push(lock);
      try {
        await handle.writeFile(owner, 'utf8');
        lock.ownerWritten = true;
      } finally {
        await handle.close();
      }
    }
    return locks;
  } catch (error) {
    await releaseOutputLocks(locks);
    throw error;
  }
}

type TrustedVerifier = { path: string; sha256: string };
async function trustedVerifier(root: string, allowedPaths: string[], recipe: { argv: string[]; trusted_verifier?: TrustedVerifier }): Promise<{ path: string; root: string; dockerTarget: string }> {
  const verifier = recipe.trusted_verifier;
  if (!verifier || typeof verifier.path !== 'string' || !/^[^/].*$/.test(verifier.path) || !/^sha256:[a-f0-9]{64}$/i.test(verifier.sha256)) throw new Error('trusted verifier is required');
  const declaredRoot = join(root, '.omp', 'ui-delivery', 'verifiers');
  const requested = resolve(root, verifier.path);
  if (!strictlyUnder(declaredRoot, requested) || allowedPaths.some((allowed) => under(resolve(root, allowed), requested))) throw new Error('trusted verifier path is unsafe');
  let current = root;
  for (const part of ['.omp', 'ui-delivery', 'verifiers']) {
    current = join(current, part);
    const stat = await lstat(current);
    const actual = await realpath(current);
    if (!stat.isDirectory() || stat.isSymbolicLink() || !strictlyUnder(root, actual)) throw new Error('trusted verifier root is unsafe');
  }
  const verifierRoot = await realpath(declaredRoot);
  const stat = await lstat(requested);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('trusted verifier path is unsafe');
  const actual = await realpath(requested);
  if (!strictlyUnder(verifierRoot, actual)) throw new Error('trusted verifier escapes protected root');
  const digest = `sha256:${createHash('sha256').update(await readFile(actual)).digest('hex')}`;
  if (digest !== verifier.sha256.toLowerCase()) throw new Error('trusted verifier digest mismatch');
  const verifierArgument = recipe.argv.some((argument, index) => {
    if (index > 1) return false;
    const path = argument.startsWith('/repo/') ? join(root, argument.slice('/repo/'.length)) : resolve(root, argument);
    return path === requested || path === actual;
  });
  if (!verifierArgument) throw new Error('trusted verifier is not the recipe entrypoint');
  const executable = recipe.argv[0];
  const executablePath = executable.startsWith('/repo/') ? join(root, executable.slice('/repo/'.length)) : resolve(root, executable);
  if (allowedPaths.some((allowed) => under(resolve(root, allowed), executablePath))) throw new Error('candidate executable is forbidden');
  return { path: actual, root: verifierRoot, dockerTarget: '/trusted-verifier' };
}

async function executeDirect(command: Command, outputLimitBytes: number, signal?: AbortSignal): Promise<Execution> {
  if (signal?.aborted) throw new Error('check aborted');
  return new Promise((resolveResult, rejectResult) => {
    const child = spawn(command.executable, command.argv, { cwd: command.cwd, env: command.env, shell: false, stdio: ['ignore', 'pipe', 'pipe'], detached: true });
    const stdoutHash = createHash('sha256'); const stderrHash = createHash('sha256'); const stdoutChunks: Buffer[] = []; const stderrChunks: Buffer[] = []; let stdoutKept = 0; let stderrKept = 0; let stdoutBytes = 0; let stderrBytes = 0; let settled = false;
    const collect = (chunks: Buffer[], kept: number, chunk: Buffer) => {
      const remaining = outputLimitBytes - kept;
      if (remaining > 0) chunks.push(Buffer.from(chunk.subarray(0, remaining)));
      return Math.min(outputLimitBytes, kept + chunk.length);
    };
    const terminate = async (reason: Error) => { if (settled) return; settled = true; clearTimeout(timer); signal?.removeEventListener('abort', aborted); try { process.kill(-child.pid!, 'SIGKILL'); } catch {} if (command.containerName) await new Promise<void>((done) => { const remover = spawn(command.executable, ['rm', '--force', command.containerName], { env: command.env, stdio: 'ignore' }); remover.once('close', () => done()); remover.once('error', () => done()); }); rejectResult(reason); };
    const aborted = () => { void terminate(new Error('check aborted')); };
    const timer = setTimeout(() => { void terminate(new Error('check timed out')); }, command.timeoutMs);
    signal?.addEventListener('abort', aborted, { once: true });
    child.stdout.on('data', (chunk: Buffer) => { stdoutHash.update(chunk); stdoutBytes += chunk.length; stdoutKept = collect(stdoutChunks, stdoutKept, chunk); });
    child.stderr.on('data', (chunk: Buffer) => { stderrHash.update(chunk); stderrBytes += chunk.length; stderrKept = collect(stderrChunks, stderrKept, chunk); });
    child.once('error', (error) => { void terminate(error); });
    child.once('close', (exitCode) => { if (settled) return; settled = true; clearTimeout(timer); signal?.removeEventListener('abort', aborted); const stdout = Buffer.concat(stdoutChunks, stdoutKept).toString(); const stderr = Buffer.concat(stderrChunks, stderrKept).toString(); resolveResult({ exitCode: exitCode ?? 1, stdout, stderr, stdoutHash: `sha256:${stdoutHash.digest('hex')}`, stderrHash: `sha256:${stderrHash.digest('hex')}`, stdoutBytes, stderrBytes, stdoutTruncated: stdoutBytes > stdoutKept, stderrTruncated: stderrBytes > stderrKept }); });
  });
}

function executeInjected(executor: (command: Command) => Promise<Execution>, command: Command, signal?: AbortSignal): Promise<Execution> {
  const { promise, resolve: resolveResult, reject: rejectResult } = Promise.withResolvers<Execution>();
  let settled = false;
  const cleanup = () => { clearTimeout(timer); signal?.removeEventListener('abort', aborted); };
  const rejectOnce = (reason: unknown) => {
    if (settled) return;
    settled = true;
    cleanup();
    rejectResult(reason);
  };
  const resolveOnce = (execution: Execution) => {
    if (settled) return;
    settled = true;
    cleanup();
    resolveResult(execution);
  };
  const aborted = () => { rejectOnce(new Error('check aborted')); };
  const timer = setTimeout(() => { rejectOnce(new Error('check timed out')); }, command.timeoutMs);
  signal?.addEventListener('abort', aborted, { once: true });
  void Promise.resolve().then(() => executor(command)).then(resolveOnce, rejectOnce);
  return promise;
}

export async function runCheck({ repo, task, checkId, command, environment = {}, executor, backends = { docker: true }, outputLimitBytes = 65536, signal, scratchRoot = tmpdir(), hostIdentity = process }: { repo: string; task: { allowed_paths: string[]; forbidden_policy_paths: string[]; approved_check_recipes: Record<string, unknown>[] }; checkId: string; command?: unknown; environment?: Record<string, string | undefined>; executor?: (command: Command) => Promise<Execution>; backends?: Record<string, boolean>; outputLimitBytes?: number; signal?: AbortSignal; scratchRoot?: string; hostIdentity?: Pick<typeof process, 'getuid' | 'getgid'> }): Promise<CheckResult> {
  if (signal?.aborted) throw new Error('check aborted');
  if (command !== undefined) throw new Error('raw commands are not accepted');
  const recipe = task.approved_check_recipes.find((entry) => entry.id === checkId) as { id: string; argv: string[]; cwd: string; timeout_ms: number; backend: 'docker'; sandbox_image: string; result_path: string; write_paths: string[]; trusted_verifier?: TrustedVerifier } | undefined;
  if (!recipe) throw new Error('unknown approved check');
  if (!Array.isArray(recipe.write_paths) || recipe.write_paths.length === 0 || typeof recipe.result_path !== 'string') throw new Error('check requires declared output paths');
  if (!backends.docker || recipe.backend !== 'docker') throw new Error('Docker is the only supported sandbox backend');
  const root = await realpath(repo);
  const cwd = resolve(root, recipe.cwd);
  if (!under(root, cwd)) throw new Error('check cwd escapes repository');
  const verifier = await trustedVerifier(root, task.allowed_paths, recipe);
  const outputPaths = new Map<string, string>();
  for (const value of recipe.write_paths) {
    const lexical = resolve(root, value);
    if (!under(root, lexical) || protectedPath(root, lexical, task.forbidden_policy_paths ?? [])) throw new Error('writable protected path');
    await validateOutputParent(root, lexical);
    outputPaths.set(value, lexical);
  }
  const locks = await acquireOutputLocks([...outputPaths.values()]);
  const outputs = new Map<string, string>();
  const protectedPaths = [...new Set(['.git', '.omp', 'secrets', ...(task.forbidden_policy_paths ?? [])])];
  let scratch: string | undefined;
  try {
    for (const [value, lexical] of outputPaths) outputs.set(value, await provisionOutput(root, lexical));
    scratch = await realpath(await mkdtemp(join(scratchRoot, 'ui-delivery-check-')));
    const masks: Mount[] = [];
    if (recipe.backend === 'docker') for (const [index, forbidden] of protectedPaths.entries()) {
      const target = resolve(root, forbidden);
      if (!under(root, target)) throw new Error('forbidden path escapes repository');
      const source = join(scratch, 'masks', String(index));
      try {
        const targetStat = await lstat(target);
        if (targetStat.isSymbolicLink() || (!targetStat.isDirectory() && !targetStat.isFile())) throw new Error('protected Docker path is unsafe');
        if (targetStat.isDirectory()) await mkdir(source, { recursive: true, mode: 0o700 });
        else { await mkdir(dirname(source), { recursive: true, mode: 0o700 }); await writeFile(source, '', { mode: 0o600, flag: 'wx' }); }
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue;
        throw error;
      }
      masks.push({ source, target: join('/repo', relative(root, target)), readOnly: true });
    }
    if (recipe.backend === 'docker') for (const [index, [, output]] of [...outputs.entries()].entries()) {
      const source = join(scratch, 'masks', `output-${index}`);
      await mkdir(dirname(source), { recursive: true, mode: 0o700 });
      await writeFile(source, '', { mode: 0o000, flag: 'wx' });
      masks.push({ source, target: join('/repo', relative(root, output)), readOnly: true });
    }
    const mounts: Mount[] = [{ source: root, target: '/repo', readOnly: true }, ...masks, { source: verifier.path, target: verifier.dockerTarget, readOnly: true }];
    for (const mount of mounts) { safeDockerMountPath(mount.source); safeDockerMountPath(mount.target); }
    const env: Record<string, string> = { PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin' };
    const containerName = `ui-delivery-${randomUUID()}`;
    const dockerUid = hostIdentity.getuid?.();
    const dockerGid = hostIdentity.getgid?.();
    if (!Number.isInteger(dockerUid) || !Number.isInteger(dockerGid) || dockerUid! <= 0 || dockerGid! <= 0) throw new Error('Docker requires non-root POSIX user IDs');
    const dockerArgv = recipe.argv.map((argument, index) => index <= 1 && (argument.startsWith('/repo/') ? join(root, argument.slice('/repo/'.length)) : resolve(root, argument)) === verifier.path ? verifier.dockerTarget : argument);
    approvedDockerRuntime(recipe.argv);
    if (!/^(?!-)[^@\s]+@sha256:[a-f0-9]{64}$/i.test(recipe.sandbox_image)) throw new Error('Docker image must be digest pinned');
    const spec: Command = {
      executable: 'docker',
      argv: ['run', '--rm', '--name', containerName, '--user', `${dockerUid}:${dockerGid}`, '--network', 'none', '--read-only', '--env', 'PATH=/usr/bin:/bin', '--env', 'HOME=/tmp/ui-delivery', '--env', 'TMPDIR=/tmp/ui-delivery', ...mounts.flatMap((mount) => ['--mount', `type=bind,source=${mount.source},target=${mount.target}${mount.readOnly ? ',readonly' : ''}`]), '--mount', 'type=tmpfs,target=/tmp/ui-delivery,tmpfs-size=67108864', '--workdir', `/repo/${recipe.cwd}`, '--', recipe.sandbox_image, ...dockerArgv],
      cwd, env, timeoutMs: recipe.timeout_ms, recipeArgv: recipe.argv, mounts, containerName,
    };
    const execution = executor
      ? await executeInjected(executor, spec, signal)
      : await executeDirect(spec, Math.max(outputLimitBytes, VERIFIER_ENVELOPE_LIMIT), signal);
    if (execution.exitCode === 0) await persistVerifierOutputs(root, verifierEnvelope(execution.stdout, recipe.write_paths, recipe.result_path), outputs, recipe.result_path);
    return { argv: recipe.argv, exitCode: execution.exitCode, stdout: output(execution.stdout, outputLimitBytes, execution.stdoutHash, execution.stdoutBytes, execution.stdoutTruncated), stderr: output(execution.stderr, outputLimitBytes, execution.stderrHash, execution.stderrBytes, execution.stderrTruncated) };
  } finally {
    if (scratch) await rm(scratch, { recursive: true, force: true });
    await releaseOutputLocks(locks);
  }
}
