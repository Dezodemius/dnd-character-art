from hashlib import sha256
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("package", ROOT / "scripts/package.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.output = Path(self.temp.name) / "output"
        for relative in package.PACKAGE_FILES:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def test_round_trip_and_no_local_files(self):
        (self.root / ".env").write_text("secret=must-not-be-packaged", encoding="utf-8")
        archive = package.build(self.root, self.output)
        with ZipFile(archive) as bundle:
            self.assertEqual(len(bundle.namelist()), 11)
            self.assertTrue(all(name.startswith("dnd-character-art/") for name in bundle.namelist()))
            self.assertFalse(any(".env" in name for name in bundle.namelist()))
            for relative in package.PACKAGE_FILES:
                self.assertEqual(bundle.read(f"dnd-character-art/{relative}"), (self.root / relative).read_bytes())
        checksum = (self.output / "SHA256SUMS.txt").read_text(encoding="ascii").split()[0]
        self.assertEqual(checksum, sha256(archive.read_bytes()).hexdigest())

    def test_reproducible_across_mtime_changes(self):
        first = package.build(self.root, self.output).read_bytes()
        for relative in package.PACKAGE_FILES:
            (self.root / relative).touch()
        self.assertEqual(first, package.build(self.root, self.output).read_bytes())

    def test_missing_reference_fails_before_output(self):
        (self.root / "assets/02-dwarf.png").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            package.build(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_invalid_png_fails(self):
        (self.root / "assets/02-dwarf.png").write_bytes(b"not an image")
        with self.assertRaisesRegex(ValueError, "PNG"):
            package.build(self.root, self.output)

    def test_four_component_versions(self):
        for version in ("0.0.0.0", "1.0.0.0", "12.34.56.789"):
            with self.subTest(version=version):
                (self.root / "VERSION").write_bytes((version + "\r\n").encode("ascii"))
                package.read_payload(self.root)

    def test_invalid_versions_fail(self):
        for version in ("1.0.0", "1.0.0.0.0", "v1.0.0.0", "1.0.0.0-beta", "01.0.0.0", "1.0.-1.0", "1.0.0.x", "1.0.0.\u0661"):
            with self.subTest(version=version):
                (self.root / "VERSION").write_bytes((version + "\r\n").encode("utf-8"))
                with self.assertRaisesRegex(ValueError, "four numeric components"):
                    package.read_payload(self.root)

    def test_lf_conversion_fails(self):
        source = self.root / "SKILL.md"
        source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        with self.assertRaisesRegex(ValueError, "CRLF"):
            package.build(self.root, self.output)


if __name__ == "__main__":
    unittest.main()
