#!/usr/bin/env python3
"""Fetch only target C files from a pinned official CHGame tool dependency.

These are external vendor inputs for local builds, not redistributed components
of our compiler archives. No downloaded host executable is run.
"""
import argparse
from pathlib import Path
import subprocess
import tarfile
import zipfile

from build_current_gcc import ROOT, sha

PACKAGES = {
    "macos": ("wch_gcc_macos-8.2.0.tar.gz",
              "https://codeload.github.com/TianpeiLee/wch_gcc_macos/tar.gz/refs/tags/8.2.0",
              "e14538ae7b621de798c2466b338a4174cce22c9cf12e5c1684c0995931738260"),
    "linux-x86_64": ("wch_gcc_8_linux-8.2.0.tar.gz",
              "https://codeload.github.com/TianpeiLee/wch_gcc_8_linux/tar.gz/refs/tags/8.2.0",
              "967fb021e5689ff79a06a71c7e54fb7face418d5e9b27ec64f5e56687557a282"),
    "windows-x86_64": ("risc-none-embed-gcc-8.2.0.zip",
              "https://codeload.github.com/openwch/risc-none-embed-gcc/zip/refs/tags/8.2.0",
              "43df880a1908c873a8b6ab115568c6beaeec41ddadeb5202703b6aa9fde50626")}


def extract_runtime(archive, destination):
    def save(name, reader):
        separator = "/riscv-none-embed/"
        if separator not in name:
            return
        relative = Path(name.split(separator, 1)[1])
        text = relative.as_posix()
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe archive path: {name}")
        wanted = (text.startswith("include/") and not text.startswith("include/c++/") or
                  text.startswith("lib/rv32imacxw/ilp32/"))
        if not wanted or relative.name.startswith(("libgcc", "libstdc++", "libsupc++")):
            return
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(reader())

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                if not entry.is_dir():
                    save(entry.filename, lambda: source.read(entry))
    else:
        with tarfile.open(archive) as source:
            for entry in source:
                if entry.isfile():
                    save(entry.name, lambda: source.extractfile(entry).read())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", choices=PACKAGES, required=True)
    ap.add_argument("--archive", type=Path, help="Use a previously downloaded pinned archive")
    args = ap.parse_args()
    name, url, digest = PACKAGES[args.host]
    work = ROOT / ".toolchains/board-runtime" / args.host
    work.mkdir(parents=True, exist_ok=True)
    archive = args.archive.resolve() if args.archive else work / name
    if not archive.exists():
        part = archive.with_name(archive.name + ".part")
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--max-time", "600",
                        url, "-o", str(part)], check=True)
        if sha(part) != digest:
            raise SystemExit("Vendor archive checksum mismatch")
        part.replace(archive)
    if sha(archive) != digest:
        raise SystemExit("Vendor archive checksum mismatch")
    destination = work / "riscv-none-embed"
    extract_runtime(archive, destination)
    print(destination)


if __name__ == "__main__":
    main()
