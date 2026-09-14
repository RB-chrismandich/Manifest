import json
import re
import subprocess
import sys
from pathlib import Path

chrome_path, target_path, png_path, result_path = sys.argv[1:]
target = Path(target_path).resolve()
png = Path(png_path).resolve()
result = Path(result_path).resolve()
profile = Path("/tmp/ui-delivery/chrome-profile")
crash_dumps = Path("/tmp/ui-delivery/crash-dumps")


def emit(passed):
    result.write_text(
        json.dumps(
            {
                "schema": "ui-delivery-check-v1",
                "required": 1,
                "passed": 1 if passed else 0,
                "failed": 0 if passed else 1,
                "skipped": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def diagnostic(value):
    text = re.sub(r"file://\S+", "[approved local target]", value)
    text = re.sub(r"https?://\S+", "[url]", text)
    return " ".join(text.split())[:4096]


try:
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    crash_dumps.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [
        chrome_path,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-javascript",
        "--no-first-run",
        "--disable-background-networking",
        "--disable-dev-shm-usage",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-crashpad",
        "--no-crash-upload",
        "--noerrdialogs",
        f"--user-data-dir={profile}",
        f"--crash-dumps-dir={crash_dumps}",
        "--hide-scrollbars",
        "--window-size=1280,900",
        f"--screenshot={png}",
        target.as_uri(),
    ]
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=25,
        check=False,
    )
    if completed.returncode != 0:
        detail = diagnostic(completed.stderr)
        raise RuntimeError(
            f"Chromium exited {completed.returncode}{': ' + detail if detail else ''}"
        )
    content = png.read_bytes()
    if len(content) <= 8 or content[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("capture is not a PNG")
    emit(True)
except Exception as error:
    sys.stderr.write(f"capture failed: {str(error)[:4080]}\n")
    emit(False)
    sys.exit(1)
