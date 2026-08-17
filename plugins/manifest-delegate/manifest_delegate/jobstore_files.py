"""Private filesystem primitives for the delegate job store."""

import hashlib
import os
import re
import shutil
import stat
import tempfile

from . import constants


def workspace_slug(cwd=None):
    cwd = cwd or os.getcwd()
    base = os.path.basename(os.path.normpath(cwd)) or "workspace"
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-").lower() or "workspace"
    digest = hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}"


def delegations_root():
    override = os.environ.get(constants.DELEGATIONS_DIR_ENV)
    if override:
        return override
    return os.path.expanduser("~/.claude/.agent_outputs/delegations")


def _mkdir_0700(path):
    os.makedirs(path, exist_ok=True)
    os.chmod(path, stat.S_IRWXU)


def _write_0600(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _atomic_write_0600(path, content):
    """Atomically replace a private file after a best-effort backup."""
    directory = os.path.dirname(path) or "."
    if os.path.isfile(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except OSError as error:
            constants.err(f"warning: could not create backup {path}.bak ({error})")
    descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError as cleanup_error:
            constants.err(
                f"warning: could not remove temp file {temporary} ({cleanup_error})"
            )
        raise


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
