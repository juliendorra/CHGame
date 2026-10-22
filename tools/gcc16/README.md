# Opt-in GCC 16.2 toolchain for CHGame Rev0

This preview ports CHGame's CH32X035 compiler support to GCC 16.2.0 and
binutils 2.47. It adds a native Apple silicon build and preserves the eight
WCH compressed byte/halfword memory forms (`Xwchc`) and
`interrupt("WCH-Interrupt-fast")`. C, C++ and LTO are supported.

The official board package remains the default. The installer selects this
compiler using reversible Arduino local overrides. The existing CHGame 0.3.0
C/printf runtime is an external dependency; it is not redistributed here.

## Status

| Host | Completed validation |
|---|---|
| macOS ARM64 | Compiler checks, 25 firmware comparisons, extracted install/restore checks, physical CHGame probe |
| macOS x86-64 | Same compiler and firmware checks under Rosetta 2, extracted install checks and actual Arduino CLI build |
| Linux x86-64 | Compiler checks and dependency audit passed; firmware comparisons in progress |
| Windows x86-64 | MinGW cross build in progress; runtime checks pending |

The 25 firmware cases include all 23 upstream examples plus two local Ball
configurations. The Ball application is outside this contribution.
See [RELEASE-VALIDATION.json](RELEASE-VALIDATION.json) and [validation/](validation/)
for the exact scope. Windows native OS/Arduino IDE integration and the complete
GNU DejaGNU suites have not been tested. This preview is not a claim of full
equivalence with undocumented WCH compiler optimizations or other WCH cores.

## Build

Run from this directory, so caches and build outputs remain here:

```sh
cd tools/gcc16
python3 tools/build_release_toolchain.py --host macos-arm64 --jobs 2 \
  --board-runtime "/path/to/Arduino15/packages/CHGame/tools/riscv-none-embed-gcc/8.2.0/riscv-none-embed"
```

Choose `macos-x86_64` on a Mac or `linux-x86_64` in an x86-64 Linux environment.
The recipe downloads SHA-256 pinned GNU/Arduino source releases and applies the
three patches in [tools/toolchain/patches/](tools/toolchain/patches/).
For the Windows Canadian cross build, prerequisites, packaging and source
archives, see [RELEASE.md](RELEASE.md). Build scripts do not activate a compiler.

## Check and install a packaged compiler

```sh
python3 tools/verify_current_gcc.py --prefix /path/to/completed/prefix \
  --reference-corpus vendor-corpus.bin --out .cache/checks
python3 tools/test_release_installer.py
```

The reference corpus contains generated machine-code test data captured from
WCH 8.2's assembler; its SHA-256 is pinned in the verifier. All 8,776 cases are
compared byte for byte. Additional checks cover standard-only output, invalid
operands, fast-interrupt frames at three optimization levels, C compression,
plain-ar slim LTO linking and a C++17 container link.

Package a completed prefix as described in [RELEASE.md](RELEASE.md). Extract the
result, then run its `tools/install_release_toolchain.py` with Python 3.10+.
The installer requires the official CHGame 0.3.0 board package, validates the
host-specific C runtime hashes and retains unrelated overrides. `--restore`
restores the original configuration. Keep the extracted compiler in place.
There are no prebuilt compiler binaries in this pull request.

## Hardware and patch review

[fixtures/PortProbe/](fixtures/PortProbe/) is a reproducible CH32X035 execution,
register-preservation and nested-interrupt probe. The recorded physical-board
run passed 64 XW cases, 20,000 register trials and 100 nested preemptions with
zero errors. Follow the upload/serial instructions in [RELEASE.md](RELEASE.md).

[PORTING.md](PORTING.md) explains the implementation boundaries and corrected
assumptions. [Patch provenance](tools/toolchain/patches/README.md) credits Andy
Lin's submitted binutils patch and David Carne's public fast-interrupt work.
Derived GNU patches use GPLv3-or-later; independent scripts/fixtures use
[MIT](LICENSE-BUILD-SCRIPTS). Component notices are retained in [licenses/](licenses/).
