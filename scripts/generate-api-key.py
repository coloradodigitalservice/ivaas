"""Generate a private UUIDv4 API key file."""

import argparse
import os
import secrets
import sys
import uuid
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new file to hold the key")
    output = parser.parse_args().output

    key = uuid.UUID(bytes=secrets.token_bytes(16), version=4)
    # New directories are accessible only to their owner.
    os.umask(0o077)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Create an owner-only file for writing; fail if it already exists.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error(f"refusing to overwrite {output}")
    # Wrap the file descriptor so the with block closes it after writing.
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(f"{key}\n")
    print(f"Key written to {output} (mode 600).", file=sys.stderr)


if __name__ == "__main__":
    main()
