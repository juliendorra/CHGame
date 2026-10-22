#!/usr/bin/env python3
"""Build native GCC 16.2 + binutils 2.47 with CHGame's WCH extensions.

Shared source/build helpers for build_release_toolchain.py.
The installed board package supplies the same target C runtime as the vendor
baseline; the compiler, binutils and libgcc are rebuilt from current sources.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".toolchains/current"
SOURCES = WORK / "src"
DOWNLOADS = WORK / "downloads"
PREFIX = WORK / "native"
TARGET = "riscv-none-elf"
ARCH = "rv32imac_zicsr_xwchc"
PATCHES = ROOT / "tools/toolchain/patches"
PACKAGES = [
    ("gcc-16.2.0.tar.xz", "https://mirrors.kernel.org/gnu/gcc/gcc-16.2.0/gcc-16.2.0.tar.xz",
     "e6738e29597f733270731aa90600f37ffdc045079dfc27ec7e8192cc81085c3e"),
    ("binutils-2.47.tar.xz", "https://mirrors.kernel.org/gnu/binutils/binutils-2.47.tar.xz",
     "154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff"),
    ("gmp-6.2.1.tar.bz2", "https://mirrors.kernel.org/gnu/gmp/gmp-6.2.1.tar.bz2",
     "eae9326beb4158c386e39a356818031bd28f3124cf915f8c5b1dc4c7a36b4d7c"),
    ("mpfr-4.1.0.tar.bz2", "https://mirrors.kernel.org/gnu/mpfr/mpfr-4.1.0.tar.bz2",
     "feced2d430dd5a97805fa289fed3fc8ff2b094c02d05287fd6133e7f1f0ec926"),
    ("mpc-1.2.1.tar.gz", "https://mirrors.kernel.org/gnu/mpc/mpc-1.2.1.tar.gz",
     "17503d2c395dfcf106b622dc142683c1199431d095367c6aacba6eec30340459"),
]
CTAGS_PACKAGE = (
    "ctags-5.8-arduino11.tar.xz",
    "https://github.com/arduino/ctags/releases/download/5.8-arduino11/ctags-5.8-arduino11.tar.xz",
    "9591ce86efa2ff7c277561706e6ace376201c5ec5f0b3925c50884ebf365d7e7",
)


def sha(path):
    with path.open("rb") as f:
        digest = hashlib.sha256()
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def environment():
    env = dict(os.environ)
    env.update(TMPDIR=str(ROOT / ".cache/tmp"), CC="/usr/bin/clang", CXX="/usr/bin/clang++",
               CFLAGS="-O1 -g0", CXXFLAGS="-O1 -g0", MAKEINFO="true",
               PATH=str(PREFIX / "bin") + os.pathsep + env.get("PATH", ""))
    return env


def command(args, cwd, log, env):
    print(f"{time.strftime('%H:%M:%S')} {log.name}", flush=True)
    with log.open("a") as stream:
        stream.write("\nCOMMAND " + repr([str(a) for a in args]) + "\n")
        stream.flush()
        result = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print("\n".join(log.read_text(errors="replace").splitlines()[-35:]), file=sys.stderr)
        raise SystemExit(result.returncode)


def prepare(env):
    for name, url, digest in PACKAGES:
        archive = DOWNLOADS / name
        previous = ROOT / ".toolchains/downloads" / name
        if not archive.exists() and previous.exists():
            shutil.copy2(previous, archive)
        if not archive.exists():
            partial = archive.with_suffix(archive.suffix + ".part")
            command(["curl", "--fail", "--location", "--retry", "3", "--max-time", "600",
                     url, "-o", partial], ROOT, WORK / "downloads.log", env)
            if sha(partial) != digest:
                raise SystemExit(f"Source checksum mismatch: {partial}")
            partial.replace(archive)
        if sha(archive) != digest:
            raise SystemExit(f"Source checksum mismatch: {archive}")
        folder = name.removesuffix(".tar.xz").removesuffix(".tar.bz2").removesuffix(".tar.gz")
        if not (SOURCES / folder / "configure").exists():
            command(["tar", "-xf", archive, "-C", SOURCES], ROOT, WORK / "extract.log", env)
    gcc = SOURCES / "gcc-16.2.0"
    for folder in ("gmp-6.2.1", "mpfr-4.1.0", "mpc-1.2.1"):
        link = gcc / folder.split("-")[0]
        if not link.exists():
            link.symlink_to(Path("..") / folder)
    for source, patch, marker, file in (
        ("binutils-2.47", "binutils-2.47-xwchc.patch", "INSN_CLASS_XWCHC", "opcodes/riscv-opc.c"),
        ("gcc-16.2.0", "gcc-16.2-wch-fast-interrupt.patch", "WCH_FAST_MODE", "gcc/config/riscv/riscv.cc"),
        ("gcc-16.2.0", "gcc-16.2-xwchc.patch", "/* NAME */ xwchc", "gcc/config/riscv/riscv-ext.def"),
    ):
        if marker not in (SOURCES / source / file).read_text():
            command(["patch", "--batch", "--forward", "-p1", "-i", PATCHES / patch],
                    SOURCES / source, WORK / "patch.log", env)

    # Keep libc/printf constant for the initial compiler equivalence study.
    # These are RISC-V objects, not Intel host programs. None is executed here.
    vendor = ROOT / ".arduino15/packages/CHGame/tools/riscv-none-embed-gcc/8.2.0/riscv-none-embed"
    sysroot = PREFIX / TARGET
    if not (sysroot / "lib/libc_nano.a").exists():
        if not (vendor / "lib/rv32imacxw/ilp32/libc_nano.a").exists():
            raise SystemExit("Install CHGame:ch32v@0.3.0 for the vendor runtime baseline")
        shutil.copytree(vendor / "include", sysroot / "include", dirs_exist_ok=True)
        shutil.copytree(vendor / "lib/rv32imacxw/ilp32", sysroot / "lib", dirs_exist_ok=True)


def build_binutils(jobs, env):
    build = WORK / "build/binutils"
    build.mkdir(parents=True, exist_ok=True)
    if not (build / "Makefile").exists():
        command([SOURCES / "binutils-2.47/configure", f"--prefix={PREFIX}", f"--target={TARGET}",
                 "--build=aarch64-apple-darwin", "--host=aarch64-apple-darwin",
                 f"--with-sysroot={PREFIX / TARGET}", "--disable-nls", "--disable-werror",
                 "--disable-gdb", "--disable-gdbserver", "--disable-sim", "--disable-gprofng",
                 "--without-debuginfod", "--disable-shared", "--with-system-zlib"],
                build, WORK / "binutils-configure.log", env)
    command(["make", f"-j{jobs}", "MAKEINFO=true"], build, WORK / "binutils-build.log", env)
    command(["make", "MAKEINFO=true", "install"], build, WORK / "binutils-install.log", env)


def build_gcc(jobs, env):
    build = WORK / "build/gcc"
    build.mkdir(parents=True, exist_ok=True)
    if not (build / "Makefile").exists():
        command([SOURCES / "gcc-16.2.0/configure", f"--prefix={PREFIX}", f"--target={TARGET}",
                 "--build=aarch64-apple-darwin", "--host=aarch64-apple-darwin",
                 "--enable-languages=c,c++", "--enable-lto", "--disable-bootstrap",
                 "--disable-multilib", "--disable-nls", "--disable-shared", "--disable-threads",
                 "--disable-libgomp", "--disable-libquadmath", "--disable-libsanitizer",
                 "--disable-libssp", "--disable-libatomic", "--disable-werror", "--without-isl",
                 "--with-newlib", "--with-gnu-as", "--with-gnu-ld", "--with-system-zlib",
                 f"--with-arch={ARCH}", "--with-abi=ilp32", "--enable-checking=release",
                 f"--with-sysroot={PREFIX / TARGET}", "--with-native-system-header-dir=/include",
                 "--with-pkgversion=CHGame native arm64 GCC 16.2 with Xwchc and WCH fast interrupts"],
                build, WORK / "gcc-configure.log", env)
    command(["make", f"-j{jobs}", "MAKEINFO=true", "configure-gcc"], build, WORK / "gcc-configure.log", env)
    command(["make", "MAKEINFO=true", "riscv-regen"], build / "gcc", WORK / "gcc-regen.log", env)
    command(["make", f"-j{jobs}", "MAKEINFO=true", "all-gcc"], build, WORK / "gcc-build.log", env)
    command(["make", "MAKEINFO=true", "install-gcc"], build, WORK / "gcc-install.log", env)
    command(["make", f"-j{jobs}", "MAKEINFO=true", "all-target-libgcc"], build, WORK / "libgcc-build.log", env)
    command(["make", "MAKEINFO=true", "install-target-libgcc"], build, WORK / "libgcc-install.log", env)


def build_stdcxx(jobs, env):
    """Install matching GCC 16 C++ headers/runtime, including nano aliases."""
    build = WORK / "build/gcc"
    flags = "-Os -g0 -ffunction-sections -fdata-sections"
    command(["make", f"-j{jobs}", "MAKEINFO=true", f"CXXFLAGS_FOR_TARGET={flags}",
             f"CFLAGS_FOR_TARGET={flags}", "all-target-libstdc++-v3"],
            build, WORK / "libstdcxx-build.log", env)
    command(["make", "MAKEINFO=true", "install-target-libstdc++-v3"],
            build, WORK / "libstdcxx-install.log", env)
    for name in ("libstdc++", "libsupc++"):
        library = PREFIX / TARGET / "lib" / (name + ".a")
        shutil.copy2(library, library.with_name(name + "_nano.a"))



if __name__ == "__main__":
    raise SystemExit("Use tools/build_release_toolchain.py --host <host> to build this kit")
