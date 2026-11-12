#!/usr/bin/env python3
"""Count synthetic NetFlow v5 probe records in a current and rotated JSONL set."""
from __future__ import annotations

import argparse
import glob
import gzip
import json
from pathlib import Path


def iter_lines(directory: Path):
    for path in sorted(glob.glob(str(directory / "flows.jsonl*"))):
        if path.endswith(".gz"):
            with gzip.open(path, "rt", errors="replace") as handle:
                yield from handle
        else:
            with open(path, "rt", errors="replace") as handle:
                yield from handle


def count_sequences(directory: Path, start: int, end: int) -> int:
    found = set()
    for line in iter_lines(directory):
        if '"SequenceNum"' not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("Type") != "NETFLOW_V5":
            continue
        if event.get("SrcAddr") != "192.0.2.10":
            continue
        if event.get("DstAddr") != "198.51.100.20":
            continue
        sequence = event.get("SequenceNum")
        if isinstance(sequence, int) and start <= sequence <= end:
            found.add(sequence)
    return len(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".data/goflow2"))
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    args = parser.parse_args()
    print(count_sequences(args.directory, args.start, args.end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
