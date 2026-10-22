#!/usr/bin/env python3
"""Check current WCH port against documented encodings and vendor binaries.

No upload. Large interrupt frames below are compile-only stress fixtures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from build_current_gcc import ARCH, PREFIX, ROOT, TARGET, WORK

OLD = ROOT / ".arduino15/packages/CHGame/tools/riscv-none-embed-gcc/8.2.0/bin/riscv-none-embed-"
OUT = WORK / "verification"
ENV = dict(os.environ, TMPDIR=str(ROOT / ".cache/tmp"))
RUNNER = []
EXE_SUFFIX = ""
REFERENCE = None
REFERENCE_SHA256 = "eb4c892f37cf2cefc19b03628b8c6110bac20aa28f87e3105dafef9fbaee4db4"


def run(args, expect=0):
    args = [str(a) for a in args]
    if args[0].startswith(str(PREFIX / "bin")):
        args[0] += EXE_SUFFIX
        if RUNNER:
            args[1:] = ["Z:" + a if a.startswith("/") else a for a in args[1:]]
            args = RUNNER + args
    p = subprocess.run(args, env=ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    if (expect == 0 and p.returncode != 0) or (expect != 0 and p.returncode == 0):
        raise RuntimeError(f"Unexpected exit {p.returncode}: {args}\n{p.stdout}")
    return p.stdout


def binary(asm, label, vendor=False, arch=ARCH):
    prefix = str(OLD) if vendor else str(PREFIX / "bin" / (TARGET + "-"))
    obj = OUT / (label + ".o")
    raw = OUT / (label + ".bin")
    run([prefix + "as", "-march=" + ("rv32imacxw" if vendor else arch),
         "-mabi=ilp32", asm, "-o", obj])
    run([prefix + "objcopy", "-O", "binary", "-j", ".text", obj, raw])
    return raw.read_bytes()


def split_instructions(data):
    instructions = []
    pos = 0
    while pos < len(data):
        half = int.from_bytes(data[pos:pos + 2], "little")
        width = 4 if half & 3 == 3 else 2
        instructions.append(data[pos:pos + width])
        pos += width
    return instructions


def verify_assembler():
    cases = []
    for op, halfword in (("lbu", False), ("sb", False), ("lhu", True), ("sh", True)):
        for reg in range(8, 16):
            for base in range(8, 16):
                for offset in range(0, 64 if halfword else 32, 2 if halfword else 1):
                    cases.append((f"{op} x{reg},{offset}(x{base})", 2))
            for offset in range(0, 32 if halfword else 16, 2 if halfword else 1):
                cases.append((f"{op} x{reg},{offset}(sp)", 2))
        # Register and immediate boundary cases which must remain ordinary.
        for reg, base in ((0, 9), (7, 9), (16, 9), (31, 9), (10, 0), (10, 7), (10, 16), (10, 31)):
            cases.append((f"{op} x{reg},0(x{base})", 4))
        for offset in ((-2048, -2, -1, 1, 31, 63, 64, 2046) if halfword else (-2048, -1, 32, 2047)):
            cases.append((f"{op} a0,{offset}(a1)", 4))
        for offset in ((-2, -1, 1, 31, 32) if halfword else (-1, 16, 31)):
            cases.append((f"{op} a0,{offset}(sp)", 4))
    source = OUT / "encoding-corpus.S"
    source.write_text(".text\n" + "\n".join(" " + c[0] for c in cases) + "\n")
    reference_bytes = REFERENCE.read_bytes() if REFERENCE else binary(source, "vendor-corpus", vendor=True)
    if hashlib.sha256(reference_bytes).hexdigest() != REFERENCE_SHA256:
        raise RuntimeError("Unexpected WCH 8.2 reference corpus; refusing an unverified oracle")
    reference = split_instructions(reference_bytes)
    actual = split_instructions(binary(source, "current-corpus"))
    if len(reference) != len(cases) or len(actual) != len(cases):
        raise RuntimeError(f"Instruction count mismatch: cases={len(cases)}, old={len(reference)}, current={len(actual)}")
    differences = []
    for case, old, new in zip(cases, reference, actual):
        if len(old) != case[1] or len(new) != case[1] or new != old:
            differences.append(dict(assembly=case[0], expected_bytes=case[1], vendor=old.hex(), current=new.hex()))
    (OUT / "encoding-differences.json").write_text(json.dumps(differences, indent=2) + "\n")
    if differences:
        raise RuntimeError(f"Encoding differences: {differences[:12]}")

    # A standard-only build must not silently emit XW encodings.
    standard = split_instructions(binary(source, "standard-corpus", arch="rv32imac_zicsr"))
    if len(standard) != len(cases) or any(len(i) != 4 for i in standard):
        raise RuntimeError("XW forms unexpectedly emitted without Xwchc")
    as_bin = PREFIX / "bin" / (TARGET + "-as")
    invalid = OUT / "invalid.S"
    negative = 0
    for instruction in ("qk.c.lbu a0,32(a1)", "qk.c.lhu a0,1(a1)", "qk.c.sb a6,0(a1)",
                        "qk.c.sh a0,64(a1)", "qk.c.lbusp a0,16(sp)", "qk.c.lhusp a0,1(sp)",
                        "qk.c.sbsp a6,0(sp)", "qk.c.shsp a0,32(sp)"):
        invalid.write_text(".text\n " + instruction + "\n")
        run([as_bin, "-march=" + ARCH, "-mabi=ilp32", invalid, "-o", OUT / "invalid.o"], expect=1)
        negative += 1
    for incompatible in ("rv32imafdc_zicsr_xwchc", "rv32imac_zicsr_zcb_xwchc"):
        run([as_bin, "-march=" + incompatible, "-mabi=ilp32", source, "-o", OUT / "invalid.o"], expect=1)
        negative += 1
    return dict(corpus_cases=len(cases), compressed_cases=sum(c[1] == 2 for c in cases),
                vendor_bytes=sum(map(len, reference)), byte_identical=True,
                reference_sha256=hashlib.sha256(reference_bytes).hexdigest(),
                standard_only_cases=len(standard), rejected_invalid_cases=negative)


def function(assembly, name):
    match = re.search(r"^" + name + r":\n(.*?)^\s*\.size\s+" + name + r",", assembly, re.M | re.S)
    if not match:
        raise RuntimeError(f"Function missing in assembly: {name}")
    return match[1]


def verify_compiler():
    cc = PREFIX / "bin" / (TARGET + "-gcc")
    source = OUT / "interrupts.c"
    preserved = [f"s{i}" for i in range(12)]
    hw = ["ra"] + [f"a{i}" for i in range(8)] + [f"t{i}" for i in range(7)]
    clobbers = ", ".join('"' + r + '"' for r in preserved + hw)
    source.write_text('extern void work(void);\n'
                      '#define IRQ __attribute__((interrupt("WCH-Interrupt-fast")))\n'
                      'IRQ void fast_leaf(void) { __asm__ volatile ("" ::: "a0", "t0"); }\n'
                      'IRQ void fast_call(void) { __asm__ volatile ("" ::: ' + clobbers + '); work(); }\n'
                      'IRQ void fast_large(void) { volatile char a[5000]; a[0]=1; a[4999]=2; work(); }\n'
                      'void ordinary(void) { work(); }\n')
    results = []
    for optimization in ("-Os", "-O2", "-O3"):
        assembly_path = OUT / ("interrupts" + optimization + ".s")
        run([cc, "-march=" + ARCH, "-mabi=ilp32", optimization, "-Werror=attributes",
             "-msave-restore", "-S", source, "-o", assembly_path])
        assembly = assembly_path.read_text()
        for name in ("fast_leaf", "fast_call", "fast_large"):
            body = function(assembly, name)
            if not re.search(r"\bmret\b", body) or re.search(r"^\s*ret\b", body, re.M):
                raise RuntimeError(f"Invalid interrupt return: {optimization} {name}")
            for reg in hw:
                if re.search(r"\b(?:sw|lw)\s+" + reg + r",\s*-?\d+\(sp\)", body):
                    raise RuntimeError(f"Redundant hardware-register spill: {optimization} {name} {reg}")
            if name == "fast_call":
                for reg in preserved:
                    for op in ("sw", "lw"):
                        if not re.search(r"\b" + op + r"\s+" + reg + r",", body):
                            raise RuntimeError(f"Missing preserved register {op} {reg}")
            results.append(dict(optimization=optimization, function=name, passed=True))
    c = OUT / "xwchc.c"
    c.write_text('#if !defined(__riscv_xwchc) || __riscv_xwchc != 1000000\n#error missing Xwchc macro\n#endif\n'
                 'unsigned byte_load(const unsigned char *p) { return *p; }\n'
                 'unsigned half_load(const unsigned short *p) { return *p; }\n'
                 'void byte_store(unsigned char *p,unsigned char v) { *p=v; }\n'
                 'void half_store(unsigned short *p,unsigned short v) { *p=v; }\n')
    obj = OUT / "xwchc.o"
    run([cc, "-march=" + ARCH, "-mabi=ilp32", "-Os", "-c", c, "-o", obj])
    dump = run([PREFIX / "bin" / (TARGET + "-objdump"), "-d", "-M", "no-aliases", obj])
    (OUT / "xwchc-disassembly.txt").write_text(dump)
    for op in ("qk.c.lbu", "qk.c.lhu", "qk.c.sb", "qk.c.sh"):
        if op not in dump:
            raise RuntimeError(f"C compiler did not produce {op}")
    # Match Arduino's plain-ar archive path, not just direct object linking.
    library_source = OUT / "lto-library.c"
    main_source = OUT / "lto-main.c"
    library_source.write_text('int exported(int x) { return x + 7; }\n')
    main_source.write_text('extern int exported(int); volatile int result;\n'
                           'void _start(void) { result=exported(5); for (;;) __asm__ volatile (""); }\n')
    flags = ["-march=" + ARCH, "-mabi=ilp32", "-Os", "-flto"]
    for src in (library_source, main_source):
        run([cc, *flags, "-c", src, "-o", src.with_suffix(".o")])
    archive = OUT / "lto-library.a"
    run([PREFIX / "bin" / (TARGET + "-ar"), "rcs", archive, library_source.with_suffix(".o")])
    run([cc, *flags, "-nostdlib", "-Wl,-e,_start", main_source.with_suffix(".o"),
         archive, "-o", OUT / "lto-archive.elf"])
    cpp = OUT / "cpp17.cpp"
    cpp.write_text('#include <array>\n#include <vector>\n#include <algorithm>\n'
                   'constexpr std::array<int,3> values={3,1,2};\n'
                   'static_assert(values[0]==3);\n'
                   'int main() { std::vector<int> v(values.begin(),values.end());\n'
                   'std::sort(v.begin(),v.end()); return v[0]!=1; }\n')
    run([PREFIX / "bin" / (TARGET + "-g++"), "-march=" + ARCH, "-mabi=ilp32", "-Os",
         "-std=c++17", "-fno-exceptions", "-fno-rtti", "--specs=nano.specs",
         "--specs=nosys.specs", "-nostartfiles", "-Wl,-e,main", cpp, "-o", OUT / "cpp17.elf"])
    return dict(interrupt_fixtures=results, c_memory_forms_compressed=4,
                lto_archive_link=True, cpp17_container_link=True)


def main():
    global PREFIX, OUT, RUNNER, EXE_SUFFIX, REFERENCE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assembler-only", action="store_true")
    ap.add_argument("--prefix", type=Path, default=PREFIX)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--reference-corpus", type=Path,
                    help="Previously captured vendor-corpus.bin; avoids running the legacy compiler")
    ap.add_argument("--runner", help="Windows execution runner, e.g. wine")
    ap.add_argument("--exe-suffix", default="")
    args = ap.parse_args()
    PREFIX, OUT, REFERENCE = args.prefix.resolve(), args.out.resolve(), args.reference_corpus
    RUNNER, EXE_SUFFIX = [args.runner] if args.runner else [], args.exe_suffix
    Path(ENV["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    results = dict(assembler=verify_assembler())
    print(json.dumps(results, indent=2), flush=True)
    if not args.assembler_only:
        results["compiler"] = verify_compiler()
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("All requested compiler checks passed.", flush=True)


if __name__ == "__main__":
    main()
