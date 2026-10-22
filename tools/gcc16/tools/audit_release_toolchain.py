#!/usr/bin/env python3
"""Audit executable architectures and dynamic dependencies before packaging."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess


def output(args):
    return subprocess.check_output([str(a) for a in args], text=True, stderr=subprocess.STDOUT)


def audit(prefix, host):
    report = dict(host=host, files={}, external_dependencies=[])
    dependencies, versions = set(), set()
    for path in sorted(prefix.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            if not path.resolve().is_relative_to(prefix):
                raise RuntimeError(f"Symlink leaves toolchain: {path}")
            continue
        with path.open("rb") as stream:
            header = stream.read(64)
        rel = path.relative_to(prefix).as_posix()
        if header[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            arch = output(["lipo", "-archs", path]).strip()
            expected = "arm64" if host == "macos-arm64" else "x86_64"
            if not host.startswith("macos") or arch != expected:
                raise RuntimeError(f"Wrong host architecture: {path}: {arch}")
            deps = [line.strip().split(" (", 1)[0] for line in output(["otool", "-L", path]).splitlines()[1:]]
            for name in deps:
                if not name.startswith(("/usr/lib/", "/System/Library/")):
                    raise RuntimeError(f"Non-system Mac dependency: {path}: {name}")
            dependencies.update(deps)
            build = output(["vtool", "-show-build", path])
            minos = re.search(r"minos\s+(\S+)", build)
            report["files"][rel] = dict(architecture=arch, dependencies=deps,
                                      minimum_macos=minos[1] if minos else None)
        elif header[:4] == b"\x7fELF":
            machine = struct.unpack_from("<H", header, 18)[0]
            if machine == 243 and (rel.startswith("riscv-none-elf/lib/") or rel.startswith("lib/gcc/")):
                continue
            if host != "linux-x86_64" or machine != 62:
                raise RuntimeError(f"Wrong ELF machine {machine}: {path}")
            dynamic = output(["readelf", "-d", path])
            deps = re.findall(r"Shared library: \[(.*?)\]", dynamic)
            dependencies.update(deps)
            info = output(["readelf", "--version-info", path])
            versions.update(re.findall(r"\b(?:GLIBCXX|GLIBC|CXXABI|GCC)_[0-9.]+", info))
            report["files"][rel] = dict(architecture="x86_64", dependencies=deps)
        elif header[:2] == b"MZ":
            with path.open("rb") as stream:
                stream.seek(struct.unpack_from("<I", header, 60)[0])
                pe = stream.read(6)
            if host != "windows-x86_64" or pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 4)[0] != 0x8664:
                raise RuntimeError(f"Wrong Windows executable architecture: {path}")
            deps = re.findall(r"DLL Name:\s*(\S+)", output(["x86_64-w64-mingw32-objdump", "-p", path]))
            dependencies.update(deps)
            for name in deps:
                if name.lower().startswith(("libgcc", "libstdc++", "libwinpthread", "zlib")):
                    if not (path.parent / name).exists() and not (prefix / "bin" / name).exists():
                        raise RuntimeError(f"Unbundled MinGW dependency: {path}: {name}")
            report["files"][rel] = dict(architecture="x86_64", dependencies=deps)
    if not report["files"]:
        raise RuntimeError("No host executables found")
    report["external_dependencies"] = sorted(dependencies)
    report["versioned_symbols"] = sorted(versions)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefix", type=Path, required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = audit(args.prefix.resolve(), args.host)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Audited {len(result['files'])} {args.host} host binaries; dependencies: {result['external_dependencies']}")


if __name__ == "__main__":
    main()
