# Porting notes and limits

This contribution targets integer-only CHGame Rev0 / CH32X035, not all QingKe
processors. The modern ISA string is `rv32imac_zicsr_xwchc`, with ILP32 ABI.

## WCH support

The binutils patch rebases Andy Lin's public Xwchc submission onto binutils
2.47. Its eight forms are byte/halfword loads and stores, each with a compact
register base or stack-pointer base. These shorten selected memory operations
from four bytes to two. GAS can compress ordinary compiler-emitted operations.
Their encodings overlap compressed floating-point instructions; incompatible
D/Zcb combinations are rejected. Names use `qk.c.*` rather than vendor `c.*`.

GCC declares Xwchc and its feature macro. Conservative instruction-length
accounting is retained. This does not reconstruct proprietary register-allocation,
scheduling or other undocumented WCH optimizer changes.

The fast-interrupt patch adds `WCH-Interrupt-fast` to the modern RISC-V backend.
It excludes the sixteen hardware-preserved integer registers from redundant
software saves while retaining normal preservation for the remaining registers
and returning with `mret`. Large-frame temporary-register rules also matter.
The compile checks cover leaf/non-leaf/large frames at `-Os`, `-O2`, `-O3`;
5,000-byte fixtures are compile-only and must not run on CHGame's 2 KB stack.
The separate device probe checks register sentinels and two-level interrupt
nesting. Hardware configuration is still the board core's responsibility.

## Corrected assumptions

- A recent stock compiler accepting ordinary RISC-V instructions is not proof
  of WCH fast-interrupt support. The explicit backend patch and register-level
  tests establish that behavior for this target.
- Moving to GCC 16 does not imply recovery of every private WCH optimization.
  Instruction encoding and fast-interrupt behavior are separately tested.
- Smaller firmware or a higher ball count alone does not prove which optimizer
  pass helped. Both vendor GCC 8.2 and this port use WCH compressed operations;
  application/runtime changes and archive/link order can also change results.
- Modern objdump can misdecode legacy XW encodings as floating-point operations
  unless the ISA is selected correctly. The legacy `-M xw` option is removed
  from Arduino's local objdump flags for the modern toolchain.
- The C library was not upgraded. Retaining the installed vendor C/printf
  runtime isolates the compiler change. Exact corresponding vendor-patched
  newlib source has not been recovered; those files stay external.
- The Mac, Linux and Windows vendor C archives have different hashes. Each
  installer manifest is generated from that host's original board runtime.
- Checking only the GCC driver's dependencies missed Homebrew zstd in other
  tools. Optional zstd is disabled and every host binary/plugin is audited.
- Intel Mac compilation needs architecture flags at both compile and link
  stages, including GCC's build-time generators and the Arduino ctags helper.
- In a Linux-to-Windows Canadian cross build, directly invoking `riscv-regen`
  bypasses top-level make exports. Explicit `CC_FOR_BUILD`/`CXX_FOR_BUILD`
  prevent generating a Windows helper that Linux then tries to execute.
- Plain `LDFLAGS=-static` made libtool generate a static LTO archive. GCC uses
  static runtime libraries while retaining a loadable LTO plugin DLL. Plain
  `ar` needs that plugin to index Arduino's slim LTO objects correctly.
- Replaying a compile database initially changed output because it lost the
  original archive/member/link ordering. Preserving that order restored all
  25 Mac firmware matches. This was a validation harness error.
- Wine execution establishes Windows executable coverage, not a native
  Windows Arduino IDE installation. Similarly, Linux amd64 execution here
  uses Rosetta in an ARM64 VM. Environments are recorded explicitly.

The Mac rebooted during the cross-platform work on 22 October 2026, interrupting
the Windows build and Linux firmware replay. Build objects were preserved and
jobs resumed. The cause of the host reboot is not established.

LLVM remains a separate exploration. It is not included in this GCC preview.

A relocated Linux-package check also caught ctags embedding the build's TMPDIR
in its configured runtime fallback. With TMPDIR unset, it tried to create files
in an absent build directory. The portable recipe now passes
`--enable-tmpdir=/tmp` and reconfigures older ctags build directories. Both Mac
hosts and Linux pass prototype extraction without TMPDIR. The helper-only stage
also now creates prefix/bin before copying ctags into a new prefix.

The final Windows link stage revealed another Canadian-cross dependency:
GCC's specs rule calls a build-host RISC-V GCC. Merely reusing target libraries
did not supply that executable. The recipe now locates GCC 16.2 in the supplied
Linux runtime prefix or requires an explicit `--build-target-compiler`, checks
its version, and passes `GCC_FOR_TARGET` on every make invocation.
