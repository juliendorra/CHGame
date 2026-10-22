#!/usr/bin/env python3
"""Build host variants of the pinned CHGame GCC port without activating them.

Run on macOS for either Mac host; run on x86-64 Linux for Linux or MinGW.
Target libraries can be shared because they contain RISC-V code, not host code.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

import build_current_gcc as base

HOSTS = {"macos-arm64": "aarch64-apple-darwin",
         "macos-x86_64": "x86_64-apple-darwin",
         "linux-x86_64": "x86_64-pc-linux-gnu",
         "windows-x86_64": "x86_64-w64-mingw32"}


def copy_runtime(source, prefix):
    for required in ("lib/gcc/riscv-none-elf/16.2.0/libgcc.a",
                     "riscv-none-elf/include/c++/16.2.0/vector",
                     "riscv-none-elf/lib/libstdc++_nano.a", "riscv-none-elf/lib/libsupc++_nano.a"):
        if not (source / required).is_file():
            raise SystemExit(f"Incomplete GCC 16.2 target runtime: {source / required}")
    for sub in ("riscv-none-elf/include", "riscv-none-elf/lib",
                "lib/gcc/riscv-none-elf/16.2.0"):
        if (source / sub).exists():
            shutil.copytree(source / sub, prefix / sub, dirs_exist_ok=True, symlinks=True)


def finish(prefix, windows):
    suffix = ".exe" if windows else ""
    for program in (prefix / "bin").glob("riscv-none-elf-*" + suffix):
        alias = program.with_name(program.name.replace("riscv-none-elf-", "riscv-none-embed-"))
        if not alias.exists():
            if windows:
                shutil.copy2(program, alias)
            else:
                alias.symlink_to(program.name)
    plugins = prefix / "lib/bfd-plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    candidates = list((prefix / "libexec/gcc/riscv-none-elf/16.2.0").glob(
        "*lto_plugin*.dll" if windows else "*lto_plugin*.so"))
    if not candidates:
        raise SystemExit("Missing loadable LTO plugin; refusing an incomplete release")
    for plugin in candidates:
        destination = plugins / plugin.name
        if not destination.exists():
            if windows:
                shutil.copy2(plugin, destination)
            else:
                destination.symlink_to(os.path.relpath(plugin, plugins))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", choices=HOSTS, required=True)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--work", type=Path)
    ap.add_argument("--sources", type=Path)
    ap.add_argument("--target-runtime", type=Path,
                    help="Reuse matching GCC 16.2 RISC-V headers/libraries from this prefix")
    ap.add_argument("--board-runtime", type=Path,
                    help="Vendor riscv-none-embed directory with include/ and lib/rv32imacxw/ilp32/")
    ap.add_argument("--stage", choices=("all", "prepare", "binutils", "gcc", "ctags", "finish"), default="all")
    args = ap.parse_args()
    windows = args.host.startswith("windows")
    mac = args.host.startswith("macos")
    if mac != (platform.system() == "Darwin"):
        ap.error("Mac hosts build on macOS; Linux and Windows hosts build on x86-64 Linux")
    if not mac and platform.machine() not in ("x86_64", "AMD64"):
        ap.error("Use an x86-64 Linux build environment")
    if windows and not args.target_runtime:
        ap.error("Windows Canadian cross build needs --target-runtime from a completed matching build")
    base.WORK = (args.work or base.ROOT / ".toolchains/release" / args.host).resolve()
    base.PREFIX = base.WORK / "prefix"
    if args.sources:
        base.SOURCES = args.sources.resolve()
    for directory in (base.WORK, base.PREFIX, base.SOURCES, base.DOWNLOADS, base.ROOT / ".cache/tmp"):
        directory.mkdir(parents=True, exist_ok=True)
    if args.target_runtime:
        copy_runtime(args.target_runtime.resolve(), base.PREFIX)
    if args.board_runtime:
        vendor = args.board_runtime.resolve()
        shutil.copytree(vendor / "include", base.PREFIX / base.TARGET / "include", dirs_exist_ok=True)
        # Exclude old libgcc/libstdc++; rebuilt GCC libraries must win.
        for file in (vendor / "lib/rv32imacxw/ilp32").iterdir():
            if file.name.startswith(("libgcc", "libstdc++", "libsupc++")):
                continue
            if file.is_file():
                dest = base.PREFIX / base.TARGET / "lib" / file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
    env = base.environment()
    temporary = base.WORK / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(temporary)
    build = HOSTS[args.host] if mac else "x86_64-pc-linux-gnu"
    host = HOSTS[args.host]
    env.update(CC_FOR_BUILD="gcc", CXX_FOR_BUILD="g++", CFLAGS_FOR_BUILD="-O1 -g0",
               CXXFLAGS_FOR_BUILD="-O1 -g0", bfd_cv_build_exeext="no",
               lt_cv_sys_max_cmd_len="8192" if windows else "262144")
    if mac:
        arch = "arm64" if args.host.endswith("arm64") else "x86_64"
        env.update(CC="/usr/bin/clang", CXX="/usr/bin/clang++",
                   CFLAGS=f"-O1 -g0 -arch {arch}", CXXFLAGS=f"-O1 -g0 -arch {arch}",
                   CFLAGS_FOR_BUILD=f"-O1 -g0 -arch {arch}", CXXFLAGS_FOR_BUILD=f"-O1 -g0 -arch {arch}",
                   LDFLAGS=f"-arch {arch}",
                   CC_FOR_BUILD=f"/usr/bin/clang -arch {arch}",
                   CXX_FOR_BUILD=f"/usr/bin/clang++ -arch {arch}", MACOSX_DEPLOYMENT_TARGET="14.0")
        env.update({name: "/usr/bin/" + name.lower() for name in ("AR", "AS", "NM", "RANLIB", "STRIP")})
    elif windows:
        env.update(CC=host + "-gcc", CXX=host + "-g++", AR=host + "-ar",
                   NM=host + "-nm", RANLIB=host + "-ranlib", STRIP=host + "-strip",
                   LDFLAGS="-static", CXXFLAGS="-O1 -g0 -static-libgcc -static-libstdc++")
    else:
        env.update(CC="gcc", CXX="g++")
    original_command = base.command

    def command(arguments, cwd, log, environment):
        arguments = [str(a).replace("--build=aarch64-apple-darwin", "--build=" + build)
                     .replace("--host=aarch64-apple-darwin", "--host=" + host)
                     .replace("CHGame native arm64 GCC 16.2", "CHGame GCC 16.2") for a in arguments]
        if arguments[0].endswith("/configure"):
            arguments.append("--without-zstd")
        if arguments[0] == "make":
            arguments += ["CC_FOR_BUILD=" + env["CC_FOR_BUILD"],
                          "CXX_FOR_BUILD=" + env["CXX_FOR_BUILD"],
                          "CFLAGS_FOR_BUILD=" + env["CFLAGS_FOR_BUILD"],
                          "CXXFLAGS_FOR_BUILD=" + env["CXXFLAGS_FOR_BUILD"]]
            if windows:
                arguments.append("LDFLAGS=" + env["LDFLAGS"])
        if windows:
            arguments = [a for a in arguments if a != "--with-system-zlib"]
        if args.target_runtime and any(a in ("all-target-libgcc", "install-target-libgcc") for a in arguments):
            return
        original_command(arguments, cwd, log, environment)

    base.command = command
    jobs = max(1, args.jobs)
    if args.stage in ("prepare", "all"):
        base.prepare(env)
    if args.stage in ("binutils", "all"):
        base.build_binutils(jobs, env)
    if args.stage in ("gcc", "all"):
        if windows:
            # Libtool interprets plain -static as disabling loadable modules.
            # Keep runtime libraries static while allowing the LTO plugin DLL.
            env["LDFLAGS"] = "-static-libgcc -static-libstdc++ -Wl,--stack,67108864"
            plugin_build = base.WORK / "build/gcc/lto-plugin"
            if (plugin_build / ".libs/liblto_plugin.a").exists() and not list(plugin_build.glob(".libs/*.dll")):
                shutil.rmtree(plugin_build)
        base.build_gcc(jobs, env)
        if not args.target_runtime:
            base.build_stdcxx(jobs, env)
    if args.stage in ("ctags", "all"):
        if windows:
            env["LDFLAGS"] = "-static"
        name, url, digest = base.CTAGS_PACKAGE
        archive = base.DOWNLOADS / name
        cached = base.ROOT / ".toolchains/downloads" / name
        if not archive.exists() and cached.exists():
            shutil.copy2(cached, archive)
        if not archive.exists():
            command(["curl", "-fL", "--retry", "3", url, "-o", archive], base.ROOT, base.WORK / "ctags.log", env)
        if base.sha(archive) != digest:
            raise SystemExit("ctags source checksum mismatch")
        source = base.SOURCES / "ctags-5.8-arduino11"
        if not source.exists():
            command(["tar", "-xf", archive, "-C", base.SOURCES], base.ROOT, base.WORK / "ctags.log", env)
        for path in [*source.glob("*.c"), *source.glob("*.h")]:
            data = path.read_bytes()
            fixed = data.replace(b"__unused__", b"CTAGS_UNUSED").replace(b"__printf__", b"CTAGS_PRINTF")
            if fixed != data:
                path.write_bytes(fixed)
        folder = base.WORK / "build/ctags"
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder / "Makefile").exists():
            command([source / "configure", "--build=" + build, "--host=" + host,
                     "--prefix=" + str(base.PREFIX)], folder, base.WORK / "ctags.log", env)
        command(["make", f"-j{jobs}", "LDFLAGS=" + env.get("LDFLAGS", "")],
                folder, base.WORK / "ctags.log", env)
        shutil.copy2(folder / ("ctags.exe" if windows else "ctags"), base.PREFIX / "bin")
    if args.stage in ("finish", "all", "gcc"):
        finish(base.PREFIX, windows)
        (base.PREFIX / "release-build.json").write_text(json.dumps(dict(
            host=args.host, build=build, target=base.TARGET, march=base.ARCH,
            gcc="16.2.0", binutils="2.47", cflags=env["CFLAGS"], cxxflags=env["CXXFLAGS"],
            shared_target_runtime=bool(args.target_runtime)), indent=2) + "\n")


if __name__ == "__main__":
    main()
