"""Prime UV's public registry cache from hash-verified local fixture wheels.

UV owns all cache writes through `uv pip install`; cache formats are never
constructed by the fixture. A loopback TLS proxy serves only locked index
records and exact locked artifact bytes, preserving registry and artifact URLs.
"""

from __future__ import annotations

import hashlib
import html
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import tomllib
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def _locked_responses(project, wheelhouse):
    packages = tomllib.loads((project / "uv.lock").read_text())["package"]
    locked = {}
    for package in packages:
        for wheel in package.get("wheels", ()):
            name = Path(urlsplit(wheel["url"]).path).name
            locked[name] = (package, wheel)
    responses, requirements, pages = {}, [], {}
    for path in sorted(wheelhouse.glob("*.whl")):
        package, wheel = locked[path.name]
        assert package["source"] == {"registry": "https://pypi.org/simple"}
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == wheel["hash"].removeprefix(
            "sha256:"
        ), path
        assert urlsplit(wheel["url"]).hostname == "files.pythonhosted.org"
        responses[wheel["url"]] = ("application/octet-stream", data)
        pages.setdefault(package["name"], []).append(
            f'<a href="{html.escape(wheel["url"])}#sha256={wheel["hash"][7:]}">{html.escape(path.name)}</a>'
        )
        requirements.append(
            f"{package['name']}=={package['version']} --hash={wheel['hash']}"
        )
    assert requirements, "locked wheelhouse is empty"
    for name, links in pages.items():
        responses[f"https://pypi.org/simple/{name}/"] = (
            "text/html",
            ("<!doctype html>\n" + "\n".join(links)).encode(),
        )
    return responses, requirements


def _certificate(directory):
    config = directory / "tls.conf"
    config.write_text(
        "[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ca\n"
        "[dn]\nCN=observer locked fixture\n[ca]\n"
        "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n"
        "[leaf]\nbasicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=DNS:pypi.org,DNS:files.pythonhosted.org\n"
    )
    ca, ca_key = directory / "ca.pem", directory / "ca-key.pem"
    certificate, key = directory / "leaf.pem", directory / "leaf-key.pem"
    request = directory / "leaf.csr"
    openssl = shutil.which("openssl", path="/usr/bin:/bin")
    assert openssl, "local TLS fixture needs the OS openssl certificate utility"
    commands = _certificate_commands(
        openssl, config, ca, ca_key, certificate, key, request
    )
    for command in commands:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    return ca, context


def _certificate_commands(openssl, config, ca, ca_key, certificate, key, request):
    return (
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-config",
            str(config),
            "-keyout",
            str(ca_key),
            "-out",
            str(ca),
        ],
        [
            openssl,
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-config",
            str(config),
            "-keyout",
            str(key),
            "-out",
            str(request),
        ],
        [
            openssl,
            "x509",
            "-req",
            "-in",
            str(request),
            "-CA",
            str(ca),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            str(config),
            "-extensions",
            "leaf",
            "-out",
            str(certificate),
        ],
    )


@contextmanager
def _locked_proxy(responses, context):
    rejected = []

    class Artifact(BaseHTTPRequestHandler):
        def do_GET(self):
            self._serve(head=False)

        def do_HEAD(self):
            self._serve(head=True)

        def _serve(self, *, head):
            host = urlsplit("https://" + self.headers.get("Host", ""))
            url = "https://" + (host.hostname or "") + self.path
            if host.port not in (None, 443) or url not in responses:
                rejected.append(url)
                self.send_error(403, "not an exact locked fixture URL")
                return
            mime, data = responses[url]
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def log_message(self, *_args):
            return

    class Proxy(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            if self.path not in {"pypi.org:443", "files.pythonhosted.org:443"}:
                rejected.append(self.path)
                self.send_error(403)
                return
            self.send_response(200, "Connection established")
            self.end_headers()
            self.wfile.flush()
            self.connection.settimeout(30)
            with context.wrap_socket(self.connection, server_side=True) as connection:
                Artifact(connection, self.client_address, self.server)
            self.close_connection = True

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    server.daemon_threads = False
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
    assert not rejected, f"UV requested unlocked fixture resources: {rejected}"


def _networkless(argv):
    if sys.platform == "darwin":
        sandbox = Path("/usr/bin/sandbox-exec")
        assert sandbox.is_file()
        return [
            str(sandbox),
            "-p",
            "(version 1) (allow default) (deny network*)",
            *argv,
        ]
    sandbox = shutil.which("bwrap")
    assert sandbox, "offline materialization requires an OS network sandbox"
    # The ordinary root bind is nodev; UV needs a working /dev/null for children.
    return [sandbox, "--bind", "/", "/", "--dev", "/dev", "--unshare-net", "--", *argv]


def _prime(argv, cwd, env, run):
    cache = Path(env["UV_CACHE_DIR"])
    wheelhouse = Path(env["UV_FIND_LINKS"]).resolve(strict=True)
    responses, requirements = _locked_responses(cwd, wheelhouse)
    with tempfile.TemporaryDirectory(prefix="observer-cache-prime-") as temporary:
        temporary = Path(temporary)
        certificate, context = _certificate(temporary)
        pins = temporary / "requirements.txt"
        pins.write_text("\n".join(requirements) + "\n")
        prime_env = {
            key: value
            for key, value in env.items()
            if key not in {"UV_OFFLINE", "UV_NO_INDEX", "UV_FIND_LINKS"}
        }
        with _locked_proxy(responses, context) as proxy:
            prime_env.update(
                HTTPS_PROXY=proxy,
                HTTP_PROXY=proxy,
                ALL_PROXY=proxy,
                NO_PROXY="",
                SSL_CERT_FILE=str(certificate),
            )
            run(
                [
                    argv[0],
                    "pip",
                    "install",
                    "--no-config",
                    "--no-deps",
                    "--no-build",
                    "--require-hashes",
                    "--index-url",
                    "https://pypi.org/simple",
                    "--python",
                    env["UV_PYTHON"],
                    "--target",
                    str(temporary / "seed"),
                    "--requirements",
                    str(pins),
                    "--cache-dir",
                    str(cache),
                ],
                cwd=cwd,
                env=prime_env,
            )
        # Stop the only serving endpoint before either materialization phase.


def offline_materializer_run(run):
    """Wrap real UV calls; prime fresh caches, then deny all phase networking."""

    def execute(argv, *, cwd, env):
        if "UV_FIND_LINKS" not in env:
            return run(argv, cwd=cwd, env=env)
        assert env.get("UV_OFFLINE") == "1" and env.get("UV_NO_INDEX") == "1"
        if argv[1] == "sync":
            _prime(argv, Path(cwd), env, run)
        return run(_networkless(argv), cwd=cwd, env=env)

    return execute
