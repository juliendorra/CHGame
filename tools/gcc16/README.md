# GCC 16.2 preview for CHGame

Build CHGame games with GCC 16.2 instead of the supplied GCC 8.2.
Includes native Apple silicon support, plus Intel Mac, Linux and Windows
builds. WCH compressed instructions and fast interrupts are preserved.

**Why:** native Apple silicon builds, plus **5.39% faster reads, 7.12% faster
writes and 4.75% smaller firmware** when rebuilding unchanged CHSDtoUSB source
on the tested Mac/card. [Benchmark and controls](BENCHMARKS.md).

| Host | Status |
|---|---|
| Apple silicon | Compiler, 25 firmware builds and hardware probe pass |
| Intel Mac | Compiler and 25 firmware matches pass under Rosetta |
| Linux x86-64 | [Native CI passes](https://github.com/juliendorra/CHGame/actions/runs/39857532605): installation, compiler and 23 examples; 25 local firmware matches |
| Windows x86-64 | [Native CI passes](https://github.com/juliendorra/CHGame/actions/runs/39858619624): installation, compiler and 23 matching firmware images |

## Use it

[Download the preview](https://github.com/juliendorra/CHGame/releases/tag/gcc-16.2.0-chgame.1-preview).
[Installation and build instructions](RELEASE.md) cover prerequisites, the
reversible Arduino installer, all four hosts and source/binary packaging.
The existing board package supplies the C runtime; compiler binaries are kept
out of Git. To build, start in this directory:

```sh
cd tools/gcc16
python3 tools/build_release_toolchain.py --host macos-arm64 --jobs 2 \
  --board-runtime "/path/to/Arduino15/packages/CHGame/tools/riscv-none-embed-gcc/8.2.0/riscv-none-embed"
```

## Review it

- [Patches and provenance](tools/toolchain/patches/README.md)
- [Validation record](RELEASE-VALIDATION.json) and [raw results](validation/)
- [Hardware probe](fixtures/PortProbe/), with serial instructions in the release guide
- [Porting notes and corrected assumptions](PORTING.md)

Scope: CH32X035, C/C++, LTO and ILP32. The 25 firmware cases include 23 upstream
examples and two local Ball configurations. Full GNU test-suite coverage and
Windows USB/IDE testing are not claimed. Independent scripts/fixtures use
[MIT](LICENSE-BUILD-SCRIPTS); component patches retain their original licenses.
