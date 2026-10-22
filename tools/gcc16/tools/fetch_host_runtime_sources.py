#!/usr/bin/env python3
"""Fetch/check exact sources for Linux/Windows compiler host runtimes."""
import argparse
import json
from pathlib import Path
import subprocess

from build_current_gcc import ROOT, sha


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()
    lock = ROOT / "tools/toolchain/host-runtime-sources.json"
    sources = json.loads(lock.read_text())["packages"]
    folder = ROOT / ".toolchains/hosts/host-runtime-sources"
    folder.mkdir(parents=True, exist_ok=True)
    for entry in sources:
        file = folder / entry["file"]
        if not file.exists() and not args.verify_only:
            part = file.with_name(file.name + ".part")
            subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--max-time", "600",
                            entry["url"], "-o", str(part)], check=True)
            if sha(part) != entry["sha256"]:
                raise SystemExit(f"Host runtime source checksum mismatch: {part}")
            part.replace(file)
        if not file.is_file() or file.stat().st_size != entry["bytes"] or sha(file) != entry["sha256"]:
            raise SystemExit(f"Missing or invalid host runtime source: {file}")
    print(f"Verified {len(sources)} host runtime source files in {folder}")


if __name__ == "__main__":
    main()
