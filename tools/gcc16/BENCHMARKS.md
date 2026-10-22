# Measured benefit: unchanged SD-to-USB app

On 22 October 2026, the original upstream CHSDtoUSB app was rebuilt with the
vendor GCC 8.2 toolchain and this GCC 16.2 toolchain, then tested on the same
physical CHGame, SD card, Mac and USB connection. With unchanged application
source, the new toolchain improved the measured median transfer rates:

| Original CHSDtoUSB source | Read median (range), KiB/s | Write median (range), KiB/s | Firmware bytes |
|---|---:|---:|---:|
| GCC 8.2 toolchain | 447.1 (439.4–463.1) | 272.0 (201.7–277.4) | 43,072 |
| GCC 16.2 toolchain | 471.2 (467.8–491.4) | 291.4 (279.8–309.3) | 41,028 |
| Change | **+5.39%** | **+7.12%** | **-4.75%** |

This is a practical reason to offer a newer compiler alongside native host
support: an existing app can become smaller and transfer data faster without
changing its application logic. This measures the complete toolchain change,
including binutils and the compiler runtime; it does not identify a particular
GCC optimization pass as the cause.

## Build and measurement controls

- Source: CHGame commit `e1f8d05940ddb7bbef89c13326da75c003f02904`;
  `platform/board/arduino/CHGame/libraries/CHGame/examples/Apps/CHSDtoUSB`.
- CHGame board package 0.3.0, 48 MHz, USB Serial, `-Os`, no LTO, ILP32,
  FQBN `CHGame:ch32v:rev0:opt=osstd`. The equivalent ISA spellings are
  `rv32imacxw` for GCC 8.2 and `rv32imac_zicsr_xwchc` for GCC 16.2.
- Original-source inputs and normalized compilation flags matched across the
  two builds. The C/printf runtime remains the board package's vendor runtime;
  GCC 16's libgcc is rebuilt. The complete commands, image hashes and source
  hashes are retained in the build record.
- One 125,829,120-byte FAT16 card; the same preallocated 4 MiB random file was
  overwritten in 64 KiB chunks. Four write/read trials per build.
- `F_NOCACHE` was set on every descriptor. Timed writes include `fsync` and
  `F_FULLFSYNC`. Each timed read follows an unmount/remount. Flashing, initial
  allocation, remount time and Spotlight waits are outside the timings.
- A third app variant was tested as a control, in A/B/C/C/B/A order with two
  trials per pass. Under GCC 16.2, its 471.8 KiB/s read and 286.4 KiB/s write
  medians overlap the original app's ranges. No throughput benefit from that
  variant's SCSI/error-handling changes was established.
- All twelve readback SHA-256 checks passed; all device reports had zero
  read/write CRC retries and failures. Existing app/menu file hashes were
  preserved, and the temporary test file was removed.

These are end-to-end filesystem copy rates for one Mac and card, not raw USB
wire rates or a guarantee for other hosts/cards. Four trials per build do not
establish small differences as generally repeatable gains. The fresh GCC 8.2
control has the distributed image's size but a different hash; the comparison
uses the freshly rebuilt control rather than assuming how the distributed
binary was built.

Raw measurements: [sd-usb-speed.json](validation/sd-usb-speed.json).
Build controls and hashes: [sd-usb-builds.json](validation/sd-usb-builds.json).
The separate app variant is outside this compiler contribution.
