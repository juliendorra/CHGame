#!/usr/bin/env python3
"""Check a packaged Linux compiler using isolated Arduino data and all examples."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    a = ap.parse_args()
    hasher = hashlib.sha256()
    with a.archive.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(block)
    digest = hasher.hexdigest()
    if digest != a.sha256:
        raise SystemExit("Compiler archive checksum mismatch")
    work, repo = a.work.resolve(), a.repo.resolve()
    expanded = work / "Compiler with spaces"
    expanded.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-xzf", str(a.archive.resolve()), "-C", str(expanded)], check=True)
    prefix, = expanded.glob("chgame-gcc-*-linux-x86_64")
    if Path(__file__).read_text() != (prefix / "tools/test_linux_package.py").read_text():
        raise SystemExit("Use the native test helper shipped with this archive")
    proof = work / "validation"
    proof.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ARDUINO_DIRECTORIES_DATA=str(work / "Arduino data"),
               ARDUINO_DIRECTORIES_DOWNLOADS=str(work / "Arduino downloads"),
               ARDUINO_DIRECTORIES_USER=str(work / "Arduino sketches"))

    def run(*arguments, environment=env):
        subprocess.run([str(x) for x in arguments], env=environment, check=True)

    index = "https://github.com/bateske/CHGame/releases/download/v0.3.0/package_chgame_index.json"
    run("arduino-cli", "version")
    run("arduino-cli", "core", "update-index", "--additional-urls", index)
    run("arduino-cli", "core", "install", "CHGame:ch32v@0.3.0", "--additional-urls", index)
    installer = prefix / "tools/install_release_toolchain.py"
    data = env["ARDUINO_DIRECTORIES_DATA"]
    run("python3", installer, "--toolchain", prefix, "--arduino-data", data)
    run("python3", prefix / "tools/verify_current_gcc.py", "--prefix", prefix,
        "--reference-corpus", prefix / "vendor-corpus.bin", "--out", proof / "compiler checks with spaces")
    run("python3", prefix / "tools/test_release_installer.py")
    run("python3", prefix / "tools/audit_release_toolchain.py", "--prefix", prefix,
        "--host", "linux-x86_64", "--out", proof / "dependencies.json")
    run(prefix / "bin/riscv-none-embed-gcc", "--version")
    fixture = work / "ctags fixture.cpp"
    fixture.write_text("void setup() {}\nvoid loop() {}\n")
    no_tmpdir = dict(env)
    no_tmpdir.pop("TMPDIR", None)
    tags = subprocess.check_output([str(prefix / "bin/ctags"), "-u", "--language-force=c++", "-f", "-",
                                   "--c++-kinds=svpf", "--fields=KSTtzns", "--line-directives", str(fixture)],
                                  env=no_tmpdir, text=True)
    assert all(any(line.startswith(name + "\t") for line in tags.splitlines()) for name in ("setup", "loop"))
    examples = repo / "platform/board/arduino/CHGame/libraries/CHGame/examples"
    sketches = sorted([*(examples / "Games").glob("*/*.ino"), *(examples / "Apps").glob("*/*.ino")])
    assert len(sketches) == 23, len(sketches)
    results = []
    for sketch in sketches:
        run("python3", repo / "tools/chgame.py", "--sketch", sketch.parent, "build")
        database = json.loads((sketch.parent / "build/release/compile_commands.json").read_text())
        assert all(Path(c["arguments"][0]).resolve().is_relative_to(prefix) for c in database)
        image = sketch.parent / "build/release" / (sketch.name + ".bin")
        results.append(dict(sketch=sketch.stem, image_bytes=image.stat().st_size,
                            sha256=hashlib.sha256(image.read_bytes()).hexdigest(), compiler_commands_verified=len(database)))
        (proof / "firmware.json").write_text(json.dumps(results, indent=2) + "\n")
    libraries = repo / "platform/board/arduino/CHGame/libraries"
    run("arduino-cli", "compile", "--fqbn", "CHGame:ch32v:rev0:opt=oslto,rtlib=nano,periph=game",
        "--build-path", work / "PortProbe build with spaces", "--library", libraries / "CHGame",
        "--library", libraries / "CHGfx", "--library", libraries / "CHSd", prefix / "fixtures/PortProbe")
    run("python3", installer, "--toolchain", prefix, "--arduino-data", data, "--restore")
    binaries = json.loads((proof / "dependencies.json").read_text())["files"]
    hashes = {name: hashlib.sha256((prefix / name).read_bytes()).hexdigest() for name in binaries}
    report = dict(passed=True, environment=platform.platform(), machine=platform.machine(),
                  libc=platform.libc_ver(), archive_sha256=digest, compiler_checks=True,
                  installer_checks=True, ctags_checks=True, compatibility_alias=True, packaged_helper_matches=True,
                  upstream_examples=len(results), hardware_probe_compile=True,
                  physical_usb_or_ide_tested=False, binary_sha256=hashes)
    (proof / "native-linux.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Native Linux validation passed; reports in", proof)


if __name__ == "__main__":
    main()
