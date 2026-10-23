"""Build a portable, reproducible skill ZIP using only the Python standard library."""

from hashlib import sha256
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


NAME = "dnd-character-art"
ASSETS = (
    "01-satyr.png",
    "02-dwarf.png",
    "03-rogue.png",
    "04-vampire-collage.png",
    "05-fantasy-collage.png",
    "06-island-collage.png",
    "07-heaven-collage.png",
)
PACKAGE_FILES = tuple(sorted((
    "SKILL.md", "README.md", "VERSION", "agents/openai.yaml",
    *(f"assets/{name}" for name in ASSETS),
)))


def read_payload(root: Path) -> dict[str, bytes]:
    payload = {}
    for relative in PACKAGE_FILES:
        source = root / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Required regular file missing: {relative}")
        if not source.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"File escapes package directory: {relative}")
        data = source.read_bytes()
        if not data:
            raise ValueError(f"Empty file: {relative}")
        if source.suffix == ".png":
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError(f"Invalid PNG signature: {relative}")
        else:
            data.decode("utf-8")
            if data.startswith(b"\xef\xbb\xbf"):
                raise ValueError(f"UTF-8 BOM is not allowed: {relative}")
            if b"\n" in data.replace(b"\r\n", b"") or b"\r" in data.replace(b"\r\n", b""):
                raise ValueError(f"Expected CRLF line endings: {relative}")
        payload[f"{NAME}/{relative}"] = data
    skill = payload[f"{NAME}/SKILL.md"].decode("utf-8")
    if not skill.startswith(f"---\r\nname: {NAME}\r\n") or "\r\ndescription:" not in skill:
        raise ValueError("Invalid skill frontmatter")
    version = payload[f"{NAME}/VERSION"].decode("utf-8").strip()
    if not re.fullmatch(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){3}", version):
        raise ValueError("VERSION must contain four numeric components, e.g. 1.0.0.0")
    return payload


def build(root: Path, output: Path) -> Path:
    payload = read_payload(root)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{NAME}.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in payload.items():
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = ZIP_DEFLATED
            bundle.writestr(entry, data, compresslevel=9)
    with ZipFile(archive) as bundle:
        if bundle.namelist() != list(payload) or bundle.testzip() is not None:
            raise ValueError("ZIP integrity or file list validation failed")
        for name, data in payload.items():
            if bundle.read(name) != data:
                raise ValueError(f"ZIP content mismatch: {name}")
    digest = sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_bytes(f"{digest}  {archive.name}\r\n".encode("ascii"))
    return archive


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    result = build(repository, repository / "dist")
    print(f"Created and verified {result} ({result.stat().st_size} bytes)")
