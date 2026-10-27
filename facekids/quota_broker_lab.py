"""Run one experimental read-only broker request in a disposable Windows VM.

Not a Windows Service, installer, production quota broker, or login provider.
Never point this diagnostic at C:/ProgramData/FaceKids/criancas.sqlite3.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

from .quota_broker_transport_win import LAB_PIPE_PREFIX, serve_one_lab_request


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FaceKids experimental read-only broker (VM LAB ONLY)"
    )
    parser.add_argument("--vm-lab-only", action="store_true",
                        help="Required explicit opt-in; no Windows service registration")
    parser.add_argument("--database", type=Path, required=True,
                        help="Existing SQLite fixture inside facekids-quota-lab directory")
    parser.add_argument("--client-sid", required=True,
                        help="Expected token SID obtained independently from Windows")
    parser.add_argument("--child-id", type=int, required=True)
    parser.add_argument("--pipe-suffix", required=True,
                        help="Unique 32-character lower-case hex lab identifier")
    return parser.parse_args(argv)


def validate_lab_options(options: argparse.Namespace) -> tuple[str, Path, dict[str, int]]:
    if not options.vm_lab_only:
        raise ValueError("Explicit --vm-lab-only acknowledgement required")
    path = Path(options.database).resolve(strict=True)
    if "facekids-quota-lab" not in [p.casefold() for p in path.parts] or not path.is_file():
        raise ValueError("Database must be an existing lab-only SQLite fixture")
    sid = options.client_sid
    if type(sid) is not str or not re.fullmatch(r"S-1-(?:\d+-)*\d+", sid):
        raise ValueError("Expected client SID is invalid")
    if type(options.child_id) is not int or options.child_id <= 0:
        raise ValueError("Invalid enrolled child")
    suffix = options.pipe_suffix
    if type(suffix) is not str or not re.fullmatch("[0-9a-f]{32}", suffix):
        raise ValueError("Pipe suffix must be 32 lowercase hexadecimal characters")
    return LAB_PIPE_PREFIX + suffix, path, {sid: options.child_id}


def main(argv=None) -> int:
    options = parse_args(argv)
    try:
        pipe_name, path, mapping = validate_lab_options(options)
        if os.name != "nt":
            raise RuntimeError("Lab broker requires an isolated Windows host")
        print("FaceKids quota lab: read-only, one request; NO Windows installation.",
              file=sys.stderr, flush=True)
        serve_one_lab_request(
            pipe_name=pipe_name, data_path=path, enrolled_child_by_sid=mapping
        )
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Lab broker declined: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
