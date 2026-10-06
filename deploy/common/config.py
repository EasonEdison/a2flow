"""Owner-only secret loading shared by Python service hosts."""

import os
from pathlib import Path
import stat


def _required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_HOST_CONFIGURATION:" + name)
    return value


def _secret(name):
    path = Path(_required(name))
    descriptor = None
    try:
        if not path.is_absolute():
            raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name)
        descriptor = os.open(path, flags | no_follow)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077):
            raise RuntimeError("SECRET_FILE_PERMISSIONS:" + name)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            value = stream.read(4097).rstrip(b"\r\n")
    except RuntimeError:
        raise
    except OSError:
        raise RuntimeError("SECRET_FILE_UNAVAILABLE:" + name) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (not value or len(value) > 4096
            or any(byte < 0x21 or byte > 0x7e for byte in value)):
        raise RuntimeError("SECRET_FILE_INVALID:" + name)
    return value.decode("ascii")
