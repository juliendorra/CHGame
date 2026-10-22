# CHGame GCC 16.2 community preview

Release: **16.2.0-chgame.1**. GCC 16.2.0, binutils 2.47, C/C++, LTO,
`rv32imac_zicsr_xwchc`, ILP32, and `interrupt("WCH-Interrupt-fast")`.
This is an independent compiler port for CHGame 0.3.0, not an official GNU,
WCH, or CHGame release. LLVM experiments are outside this release.
These preview binaries have no Developer ID notarization or Windows signing.

## Downloads and scope

The local release directory contains one archive per validated host, a matching
`-sources.tar.gz`, a small `-patch-kit.tar.gz` for review, and SHA-256 sidecars.
The patch kit downloads the pinned upstream sources when building; the full
source archive already includes them. Check `RELEASE-VALIDATION.json` for the
actual execution environment and completed checks; a successful cross build
alone is not runtime validation. macOS requires 14.4 or newer. Linux x86-64 requires glibc 2.34 or newer and system zlib; the tools were
built and exercised on Ubuntu 22.04. Windows targets x86-64 Windows.

The binary archives contain the compiler, assembler/linker and other binutils,
GCC's rebuilt RISC-V libgcc and C++ runtime, and Arduino's ctags helper. GNU
source licenses and the GCC Runtime Library Exception accompany them. The source
archive includes the exact original GNU and ctags tarballs, prerequisites,
patches, build recipes, and checksums. Keep that archive alongside the binaries
when sharing or mirroring this preview.
It also includes the exact Ubuntu GCC 11.4/10.3, MinGW-w64 8.0 and zlib source
packages/patches for the static Linux and Windows **host** runtime libraries. These are
separate from the GCC 16.2 RISC-V libraries generated for firmware. Linux and
Windows tools link their host C++ runtimes statically.

The CHGame package supplies its existing WCH C/printf runtime and C headers.
Their exact corresponding patched source has not been recovered. These vendor
files are **not included in the compiler download**: the installer checks and
copies them from the user's installed CHGame 0.3.0 board package. This is a
documented external dependency, not a claim that newlib has been rebuilt.

The eight supported vendor memory forms are compressed byte/halfword loads and
stores, with compact-register and stack-pointer variants. These encodings collide
with floating-point compressed instructions; incompatible D/Zcb combinations are
rejected. Hardware fast-interrupt saves, software preservation of the remaining
registers, and `mret` are retained. This does not establish equivalence for every
WCH processor or every proprietary extension. Ordinary C++17 container linking
is tested; C++23 library modules remain unvalidated with the legacy C runtime.

## Install

1. Install the official CHGame **0.3.0** board package in Arduino IDE or CLI.
   Close the IDE before changing the local compiler configuration.
2. Extract the archive for your host to a persistent writable directory.
   On macOS use `tar -xzf`; on Windows use **Extract All** on the ZIP.
3. Install Python 3.10 or newer. Open a terminal in the extracted directory:

   ```sh
   python3 tools/install_release_toolchain.py
   ```

   On Windows use `py -3` in place of `python3`. If your Arduino data directory
   is nonstandard, append `--arduino-data "/path/to/Arduino15"`. Defaults are
   `~/Library/Arduino15` on macOS, `%LOCALAPPDATA%/Arduino15` on Windows, and
   `~/.arduino15` on Linux.
4. Reopen Arduino and build a CHGame sketch. Clear any old sketch/core build
   caches when changing compiler versions. The overrides select the new march,
   printf library, ctags, and compiler path together.

The installer retains unrelated override properties and backs up the original
`platform.local.txt` and `boards.local.txt`. It does not replace the board's
original 8.2 compiler. To restore the first installation's configuration:

```sh
python3 tools/install_release_toolchain.py --restore
```

Use the same `--arduino-data` option for restoration. Keep the extracted
directory in place while it is selected. `bin/riscv-none-elf-gcc --version`
should report GCC 16.2.0; `riscv-none-embed-*` compatibility names are included
for the existing Arduino recipes. On Windows these are real EXE files.

## Build from the included sources

Extract the source archive onto a filesystem with sufficient build space.
Python 3.10+, a C/C++ host compiler, GNU make, patch, curl, tar, and normal Unix
build utilities are needed. macOS uses Xcode Command Line Tools; Linux examples
use Ubuntu 22.04 x86-64 with `build-essential zlib1g-dev flex bison texinfo python3
curl patch`. No Homebrew library is linked into the Mac distribution.

The source archive already has every pinned upstream download under
`.toolchains/current/downloads`; the builder verifies their hashes before
extracting. It applies the three patches in `tools/toolchain/patches` and keeps
build output under `.toolchains`. Supply the installed vendor runtime directory:

```sh
python3 tools/build_release_toolchain.py --host macos-arm64 --jobs 2 \
  --board-runtime "/path/to/Arduino15/packages/CHGame/tools/riscv-none-embed-gcc/8.2.0/riscv-none-embed"
```

Choose `macos-x86_64` to build Intel tools on a Mac. Apple silicon can execute
them through Apple's separately installed Rosetta 2. Choose `linux-x86_64` in
an x86-64 Linux environment. Host compiler optimization affects compiler speed,
not the requested optimization of the generated firmware.

For Windows, install Ubuntu's `g++-mingw-w64-x86-64` and build on x86-64 Linux:

```sh
python3 tools/fetch_board_runtime.py --host windows-x86_64
python3 tools/build_release_toolchain.py --host windows-x86_64 --jobs 2 \
  --target-runtime "/path/to/completed/linux-x86_64/prefix" \
  --board-runtime .toolchains/board-runtime/windows-x86_64/riscv-none-embed
```

The fetch helper verifies the original board-package archive's pinned checksum
and extracts only its target C files. The three original host packages have
different runtime archive hashes; the Windows release must be tested against
the Windows package's runtime, rather than assuming the Mac archive is identical.

This is a Canadian cross build: build OS Linux, compiler host Windows, generated
code RISC-V. The matching RISC-V headers/libraries can be reused across hosts;
they contain RISC-V code. Each host's compiler executables and LTO plugin are
built separately. `--stage` supports resumable preparation/binutils/GCC/ctags
steps. Do not reuse a configured build directory for a different host or flags.

## Validate and package

From an installed/extracted prefix containing the vendor runtime:

```sh
python3 tools/verify_current_gcc.py --prefix "/path/to/prefix" \
  --reference-corpus vendor-corpus.bin --out .cache/validation
```

The saved reference is the complete 8,776-instruction corpus captured from WCH
GCC 8.2's assembler. The validator reports its SHA-256, compares every encoding,
checks standard-only output and invalid operands, compiles fast-interrupt frame
fixtures at three optimization levels, verifies C memory compression, and links
both a plain-ar LTO archive and a C++17 container program. Firmware execution
requires hardware; this script does not upload anything. Linux can additionally
exercise Windows executables under Wine with `--runner wine --exe-suffix .exe`;
that does not replace native Windows integration testing.

For a hardware check, open `fixtures/PortProbe/PortProbe.ino` with the matching
CHGame libraries, select the CHGame USB Serial option, and upload it. At 115200
baud, send `?` in the serial monitor. Expect 64 XW cases, 20,000 register trials,
zero XW/register/nesting errors, and a positive `nested_ok` count. `R` repeats
the test. Re-upload your game afterward. The fixture and its generated assembly
are included so the board author can reproduce the interrupt checks.

```sh
python3 tools/fetch_host_runtime_sources.py
python3 tools/package_release_toolchain.py --host linux-x86_64 --prefix /path/to/prefix
python3 tools/package_release_toolchain.py --sources
python3 tools/package_release_toolchain.py --patch-kit
```

The package helper's default output is `.cache/distribution/release`. Release
archives are local artifacts, not files committed into Git. Patch provenance,
upstream licenses and original authors are in `tools/toolchain/patches/README.md`.
The workspace investigation reports retain hardware evidence and failed paths.
No public repository, release, or upstream message is created by these scripts.
