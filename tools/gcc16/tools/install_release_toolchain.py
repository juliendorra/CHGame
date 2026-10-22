#!/usr/bin/env python3
"""Install an extracted toolchain for CHGame 0.3.0 using reversible overrides."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time


def data_directory():
    if platform.system() == "Darwin":
        return Path.home() / "Library/Arduino15"
    if platform.system() == "Windows":
        return Path(os.environ["LOCALAPPDATA"]) / "Arduino15"
    return Path.home() / ".arduino15"


def install(prefix, data, restore=False, check_host=True):
    core = data / "packages/CHGame/hardware/ch32v/0.3.0"
    if not (core / "platform.txt").is_file():
        raise SystemExit(f"Install CHGame:ch32v@0.3.0 first: {core}")
    marker = core / "chgame-gcc16-install.json"
    if restore:
        info = json.loads(marker.read_text())
        for name, backup in info["backups"].items():
            target = core / name
            if backup:
                shutil.copy2(core / backup, target)
            else:
                target.unlink(missing_ok=True)
        marker.unlink()
        return
    manifest = json.loads((prefix / "RELEASE.json").read_text())
    if check_host:
        machine = platform.machine().lower()
        actual = ("macos-" + ("arm64" if machine == "arm64" else "x86_64")
                  if platform.system() == "Darwin" else
                  "windows-x86_64" if platform.system() == "Windows" else
                  "linux-" + ("x86_64" if machine in ("x86_64", "amd64") else machine))
        if actual != manifest["host"]:
            raise SystemExit(f"This archive is for {manifest['host']}; running on {actual}")
        suffix = ".exe" if platform.system() == "Windows" else ""
        subprocess.run([str(prefix / "bin" / ("riscv-none-elf-gcc" + suffix)), "--version"], check=True)
    if marker.exists():
        previous = json.loads(marker.read_text())
        backups = previous["backups"]
    else:
        backups = {}
        for name in ("platform.local.txt", "boards.local.txt"):
            target = core / name
            backup = name + f".before-gcc16-{time.time_ns()}" if target.exists() else None
            if backup:
                shutil.copy2(target, core / backup)
            backups[name] = backup
    vendor = data / "packages/CHGame/tools/riscv-none-embed-gcc/8.2.0/riscv-none-embed"
    runtime = vendor / "lib/rv32imacxw/ilp32"
    # Check every file before changing the extracted sysroot or core overrides.
    for name, digest in manifest["vendor_runtime_sha256"].items():
        file = runtime / name
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"Unexpected CHGame 0.3.0 runtime: {file}")
    dest = prefix / "riscv-none-elf"
    for source in (vendor / "include").iterdir():
        if source.name == "c++":
            continue
        target = dest / "include" / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for name in manifest["vendor_runtime_sha256"]:
        (dest / "lib").mkdir(parents=True, exist_ok=True)
        shutil.copy2(runtime / name, dest / "lib" / name)
    bin_path = (prefix / "bin").as_posix()
    overrides = {
        "platform.local.txt": {"compiler.path": bin_path + "/",
            "compiler.objdump.flags": "--all-headers --demangle --disassemble",
            "runtime.tools.ctags.path": bin_path,
            "runtime.tools.ctags-5.8-arduino11.path": bin_path},
        "boards.local.txt": {"rev0.build.march": "rv32imac_zicsr_xwchc",
                              "rev0.build.ch_extra_lib": "-lprintf"}}
    for name, properties in overrides.items():
        target = core / name
        lines = target.read_text().splitlines() if target.exists() else []
        lines = [line for line in lines if line.partition("=")[0].strip() not in properties]
        lines.extend(key + "=" + value for key, value in properties.items())
        target.write_text("\n".join(lines) + "\n")
    marker.write_text(json.dumps(dict(prefix=str(prefix), backups=backups), indent=2) + "\n")
    print(f"Installed {manifest['host']} GCC 16.2 for {core}; restart Arduino IDE.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--toolchain", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--arduino-data", type=Path, default=data_directory())
    ap.add_argument("--restore", action="store_true", help="Restore the overrides saved by the first installation")
    args = ap.parse_args()
    install(args.toolchain.resolve(), args.arduino_data.resolve(), args.restore)


if __name__ == "__main__":
    main()
