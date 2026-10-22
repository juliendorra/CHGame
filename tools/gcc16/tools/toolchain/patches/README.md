# Current GCC WCH patch series

The current port targets CHGame Rev0's integer-only CH32X035, with portable host
build recipes. Validation results belong in `../../../RELEASE-VALIDATION.json`; the existence
of these patches alone does not establish hardware equivalence.

Apply in this order to the named pristine releases:

1. `binutils-2.47-xwchc.patch` to binutils 2.47.
2. `gcc-16.2-xwchc.patch` to GCC 16.2.0.
3. `gcc-16.2-wch-fast-interrupt.patch` to GCC 16.2.0.

The three GCC/binutils patches modify GNU software and are distributed under
GPL version 3 or later, consistent with those projects. See [COPYING3](COPYING3). Original
copyrights and authorship remain applicable.

## Provenance

The binutils patch derives from Andy Lin's public v2 submission of 24 November
2025:
https://sourceware.org/pipermail/binutils/2025-November/145893.html

`binutils-xwchc-upstream.patch` preserves that submitted diff. The 2.47 rebase
updates extension tables, parser locations, validation and option handling;
it retains the upstream opcode definitions and tests. Its naming is `Xwchc`
and `qk.c.*`, following the modern implementation, rather than the legacy
vendor spelling `xw` / `c.*`. Ordinary C loads/stores are compressed by GAS.
The source is a submitted patch, not a claim of upstream acceptance.

The GCC fast-interrupt port follows the approach in David Carne's patch as
published by HydraUSB3 for GCC 12.2:
https://github.com/hydrausb3/riscv-none-elf-gcc-xpack/blob/b9b8527/patches/gcc-12.2.0.patch.diff

The 16.2 port uses an explicit list of the sixteen hardware-preserved integer
registers, preserves the remaining register-save rules, handles large-frame
temporary registers and returns with `mret`. It includes attribute documentation
and a compiler regression fixture. Tests for this project do not establish
support for every QingKe core, floating-point ABI or nesting configuration.

The GCC Xwchc patch adds the extension declaration, generated option state,
extension documentation and a regression fixture. Existing GAS compression
performs instruction encoding; the compiler's conservative length accounting
is retained, as for ordinary compressed instructions. This is not a recovered
copy of WCH's undocumented GCC optimizer changes.

## Build and verification

From `tools/gcc16`, follow [the kit README](../../../README.md) for portable
build and verification commands. [The release guide](../../../RELEASE.md)
describes installation, source packaging and hardware checks. Completed results
and execution limits are in [the validation record](../../../RELEASE-VALIDATION.json).
The reference assembler corpus and device fixtures are included in the kit.

Source downloads were checked against official detached GNU signatures using
the GNU keyring. GCC's signing key was
`7F74F97C103468EE5D750B583AB00996FC26A641`; binutils' was
`3A24BC1E8FB409FA9F14371813FCEF89DD9E3C4F`. Build recipes pin archive hashes.

## Arduino helper portability

`ctags-5.8-arduino11-tempdir.patch` applies to Arduino ctags 5.8-arduino11.
It retains the original TMPDIR override and uses Windows TEMP/TMP when that
override is absent. This derived ctags change is GPL-2.0-or-later, consistent
with ctags' own COPYING notice in the release licenses/ctags directory. The
build recipe also uses /tmp as the POSIX fallback and renames two reserved
macro identifiers which conflict with current Apple SDK headers.
