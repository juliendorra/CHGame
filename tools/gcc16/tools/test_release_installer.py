#!/usr/bin/env python3
"""Exercise install, reinstall, restoration and runtime mismatch in isolation."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from install_release_toolchain import install


class InstallerTest(unittest.TestCase):
    def test_install_restore_and_reject_wrong_runtime(self):
        root = Path(__file__).resolve().parents[1] / ".cache/tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root, prefix="installer test ") as folder:
            base = Path(folder)
            data, prefix = base / "Arduino data", base / "compiler with spaces"
            core = data / "packages/CHGame/hardware/ch32v/0.3.0"
            core.mkdir(parents=True)
            (core / "platform.txt").write_text("name=CHGame\n")
            original = "# existing settings\ncustom.value=keep\ncompiler.path=old/\n"
            (core / "platform.local.txt").write_text(original)
            runtime = data / "packages/CHGame/tools/riscv-none-embed-gcc/8.2.0/riscv-none-embed"
            (runtime / "lib/rv32imacxw/ilp32").mkdir(parents=True)
            (runtime / "include/c++/8.2.0").mkdir(parents=True)
            (runtime / "include/stdio.h").write_text("/* fixture */\n")
            library = runtime / "lib/rv32imacxw/ilp32/libc.a"
            library.write_bytes(b"fixture runtime")
            prefix.mkdir()
            (prefix / "RELEASE.json").write_text(json.dumps(dict(host="test", vendor_runtime_sha256={
                "libc.a": hashlib.sha256(library.read_bytes()).hexdigest()})))
            install(prefix, data, check_host=False)
            changed = (core / "platform.local.txt").read_text()
            self.assertIn("custom.value=keep", changed)
            self.assertIn(prefix.as_posix() + "/bin/", changed)
            self.assertIn("xwchc", (core / "boards.local.txt").read_text())
            self.assertFalse((prefix / "riscv-none-elf/include/c++/8.2.0").exists())
            install(prefix, data, check_host=False)
            self.assertEqual((core / "platform.local.txt").read_text(), changed)
            install(prefix, data, restore=True)
            self.assertEqual((core / "platform.local.txt").read_text(), original)
            self.assertFalse((core / "boards.local.txt").exists())
            library.write_bytes(b"wrong version")
            with self.assertRaisesRegex(SystemExit, "Unexpected CHGame"):
                install(prefix, data, check_host=False)
            self.assertEqual((core / "platform.local.txt").read_text(), original)
            self.assertFalse((core / "chgame-gcc16-install.json").exists())


if __name__ == "__main__":
    unittest.main()
