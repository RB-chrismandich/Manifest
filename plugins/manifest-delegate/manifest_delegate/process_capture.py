"""Bounded subprocess stream capture for delegated backends."""

import contextlib
import threading

MAX_CAPTURED_OUTPUT_BYTES = 65_536
MAX_FAILURE_STREAM_BYTES = 65_536
DRAIN_GRACE_SECONDS = 5
SESSION_CAPTURE_HEAD_BYTES = 16_384
STDOUT_CAPTURE_TAIL_BYTES = MAX_CAPTURED_OUTPUT_BYTES - SESSION_CAPTURE_HEAD_BYTES


class _BoundedTail:
    """Keep a thread-safe, size-capped tail of an arbitrary byte stream."""

    def __init__(self, cap):
        self._cap = cap
        self._buf = bytearray()
        self._lock = threading.Lock()
        self.truncated = False

    def feed(self, chunk):
        with self._lock:
            self._buf += chunk
            if len(self._buf) > self._cap:
                self.truncated = True
                del self._buf[: len(self._buf) - self._cap]

    def value(self):
        with self._lock:
            return bytes(self._buf)


class _BoundedHead:
    """Keep a thread-safe, size-capped head of an arbitrary byte stream."""

    def __init__(self, cap):
        self._cap = cap
        self._buf = bytearray()
        self._total = 0
        self._lock = threading.Lock()

    def feed(self, chunk):
        with self._lock:
            self._total += len(chunk)
            room = self._cap - len(self._buf)
            if room > 0:
                self._buf += chunk[:room]

    def value(self):
        with self._lock:
            return bytes(self._buf)

    @property
    def total_bytes(self):
        with self._lock:
            return self._total


def _drain_into(stream, sinks):
    """Read a stream to EOF while feeding each bounded capture sink."""
    while True:
        try:
            chunk = stream.read(65536)
        except (ValueError, OSError):
            break
        if not chunk:
            break
        for sink in sinks:
            sink.feed(chunk)


def _feed_stdin(stdin, payload):
    """Feed subprocess stdin without letting an early close deadlock the caller."""
    with contextlib.suppress(BrokenPipeError, OSError):
        stdin.write(payload)
        stdin.close()
