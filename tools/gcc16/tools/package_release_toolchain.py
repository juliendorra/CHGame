#!/usr/bin/env python3
"""Make standalone compiler archives and their matching source distribution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import zipfile

import build_current_gcc as base

VERSION = "16.2.0-chgame.1"
PATCH_NAMES = ("binutils-2.47-xwchc.patch", "gcc-16.2-xwchc.patch",
               "gcc-16.2-wch-fast-interrupt.patch", "binutils-xwchc-upstream.patch", "README.md", "COPYING3")
SCRIPTS = ("build_current_gcc.py", "build_release_toolchain.py", "verify_current_gcc.py",
           "install_release_toolchain.py", "package_release_toolchain.py", "fetch_board_runtime.py",
           "audit_release_toolchain.py", "fetch_host_runtime_sources.py", "test_release_installer.py", "test_windows_package.ps1")


def support(root):
    lock = base.ROOT / "tools/toolchain/host-runtime-sources.json"
    lock_dest = root / "tools/toolchain/host-runtime-sources.json"
    lock_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lock, lock_dest)
    for name in SCRIPTS:
        dest = root / "tools" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base.ROOT / "tools" / name, dest)
    for name in PATCH_NAMES:
        dest = root / "tools/toolchain/patches" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base.PATCHES / name, dest)
    for name in ("RELEASE.md", "RELEASE-VALIDATION.json", "BENCHMARKS.md", "PORTING.md"):
        source = base.ROOT / "tools/toolchain" / name
        if not source.exists():
            source = base.ROOT / name
        if source.exists():
            shutil.copy2(source, root / name)
    if (root / "RELEASE.md").exists():
        shutil.copy2(root / "RELEASE.md", root / "README.md")
    evidence = base.ROOT / "tools/toolchain/release-evidence"
    if not evidence.exists():
        evidence = base.ROOT / "validation"
    if evidence.exists():
        shutil.copytree(evidence, root / "validation", dirs_exist_ok=True)
    fixtures = base.ROOT / "tools/toolchain/fixtures"
    if not fixtures.exists():
        fixtures = base.ROOT / "fixtures"
    for name in ("PortProbe/PortProbe.ino", "PortProbe/probes.S", "generate_port_probe.py"):
        dest = root / "fixtures" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixtures / name, dest)
    containerfile = base.ROOT / "tools/toolchain/Containerfile"
    if not containerfile.exists():
        containerfile = base.ROOT / "Containerfile"
    shutil.copy2(containerfile, root / "Containerfile")
    script_license = base.ROOT / "tools/toolchain/LICENSE-BUILD-SCRIPTS"
    if not script_license.exists():
        script_license = base.ROOT / "LICENSE-BUILD-SCRIPTS"
    shutil.copy2(script_license, root / "LICENSE-BUILD-SCRIPTS")
    reference = base.WORK / "verification/vendor-corpus.bin"
    if not reference.exists():
        reference = base.ROOT / "vendor-corpus.bin"
    if reference.exists():
        shutil.copy2(reference, root / "vendor-corpus.bin")
    notices = base.ROOT / "tools/toolchain/licenses"
    if not notices.exists():
        notices = base.ROOT / "licenses"
    shutil.copytree(notices, root / "licenses", dirs_exist_ok=True)


def checksums(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def archive(root, destination, windows=False):
    if windows:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    z.write(path, root.name + "/" + path.relative_to(root).as_posix())
    else:
        with tarfile.open(destination, "w:gz", compresslevel=6) as t:
            t.add(root, arcname=root.name)
    digest = base.sha(destination)
    destination.with_name(destination.name + ".sha256").write_text(f"{digest}  {destination.name}\n")
    print(f"{destination}: {destination.stat().st_size:,} bytes; SHA256 {digest}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", choices=("macos-arm64", "macos-x86_64", "linux-x86_64", "windows-x86_64"))
    ap.add_argument("--prefix", type=Path)
    ap.add_argument("--sources", action="store_true")
    ap.add_argument("--patch-kit", action="store_true", help="Small review/build kit without upstream tarballs or binaries")
    ap.add_argument("--destination", type=Path, default=base.ROOT / ".cache/distribution/release")
    args = ap.parse_args()
    if sum((args.sources, args.patch_kit, bool(args.host))) != 1:
        ap.error("Choose --sources, --patch-kit, or --host with --prefix")
    if args.host and not args.prefix:
        ap.error("--host requires --prefix")
    dest = args.destination.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    kind = "sources" if args.sources else "patch-kit" if args.patch_kit else args.host
    name = "chgame-gcc-" + VERSION + "-" + kind
    root = dest / "staging" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    if args.sources:
        for file, url, digest in [*base.PACKAGES, base.CTAGS_PACKAGE]:
            candidates = [base.DOWNLOADS / file, base.ROOT / ".toolchains/downloads" / file]
            source = next((p for p in candidates if p.exists()), None)
            if not source or base.sha(source) != digest:
                raise SystemExit(f"Missing or invalid source archive: {file}")
            target = root / ".toolchains/current/downloads" / file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        lock = json.loads((base.ROOT / "tools/toolchain/host-runtime-sources.json").read_text())
        for entry in lock["packages"]:
            source = base.ROOT / ".toolchains/hosts/host-runtime-sources" / entry["file"]
            if not source.exists() or base.sha(source) != entry["sha256"]:
                raise SystemExit("Run tools/fetch_host_runtime_sources.py before packaging sources")
            target = root / ".toolchains/hosts/host-runtime-sources" / entry["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    elif args.host:
        prefix = args.prefix.resolve()
        if not (prefix / "bin" / ("riscv-none-elf-gcc.exe" if args.host.startswith("windows") else "riscv-none-elf-gcc")).is_file():
            raise SystemExit("Incomplete compiler prefix")
        # Distribute GNU-built components only. Vendor C headers and libraries
        # are supplied by the user's original board installation at install time.
        def ignore(folder, names):
            rel = Path(folder).relative_to(prefix).as_posix()
            if rel == "riscv-none-elf/include":
                return [n for n in names if n != "c++"]
            if rel == "riscv-none-elf/include/c++":
                return [n for n in names if n != "16.2.0"]
            if rel == "riscv-none-elf/lib":
                return [n for n in names if not (n.startswith(("libstdc++", "libsupc++")) and n.endswith(".a"))]
            return [n for n in names if n in ("chgame-current.json", "__pycache__")]
        shutil.copytree(prefix, root, dirs_exist_ok=True, symlinks=not args.host.startswith("windows"), ignore=ignore)
        runtime = prefix / "riscv-none-elf/lib"
        vendor_names = [p.name for p in runtime.iterdir() if p.is_file()
                        and not p.name.startswith(("libstdc++", "libsupc++", "libgcc"))]
        manifest = dict(version=VERSION, host=args.host, target=base.TARGET, march=base.ARCH,
                        gcc="16.2.0", binutils="2.47", wch_fast_interrupts=True,
                        vendor_runtime_sha256={n: base.sha(runtime / n) for n in sorted(vendor_names)},
                        vendor_runtime="External CHGame 0.3.0 RV32IMACXW dependency; not included",
                        upstream_board_commit="e1f8d05940ddb7bbef89c13326da75c003f02904",
                        patches={n: base.sha(base.PATCHES / n) for n in PATCH_NAMES[:3]})
        (root / "RELEASE.json").write_text(json.dumps(manifest, indent=2) + "\n")
    support(root)
    (root / "SHA256SUMS.json").write_text(json.dumps(checksums(root), indent=2) + "\n")
    windows = args.host == "windows-x86_64"
    archive(root, dest / (name + (".zip" if windows else ".tar.gz")), windows)


if __name__ == "__main__":
    main()
