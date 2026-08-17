"""Descriptor-relative filesystem primitives for capability rollback."""

import ctypes
import os


def _exchange_directory_entries(
    source_descriptor: int,
    source_name: str,
    destination_descriptor: int,
    destination_name: str,
) -> None:
    """Atomically exchange two directory entries without a check-then-act gap."""
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    renameat2 = getattr(library, "renameat2", None)
    if renameat2 is not None:
        result = renameat2(
            source_descriptor,
            source,
            destination_descriptor,
            destination,
            2,
        )
    else:
        renameatx_np = getattr(library, "renameatx_np", None)
        if renameatx_np is None:
            raise OSError("atomic directory-entry exchange is unavailable")
        result = renameatx_np(
            source_descriptor,
            source,
            destination_descriptor,
            destination,
            0x00000002,
        )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))
