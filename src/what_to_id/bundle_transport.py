"""Transport verified bundles as bounded release assets without changing their bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from what_to_id.artifacts import load_bundle
from what_to_id.manifest import sha256_file

MANIFEST = "bundle_transport.json"
PART_BYTES = 1024**3
BLOCK_BYTES = 1024**2


def _plain(name: str) -> str:
    if not isinstance(name, str) or name in {"", ".", ".."} or Path(name).name != name:
        raise ValueError("transport files must be plain filenames")
    if "\\" in name:
        raise ValueError("transport files must be plain filenames")
    return name


def _destination(out: Path) -> None:
    if out.exists() or out.is_symlink():
        raise ValueError(f"destination already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)


def stage_release(bundle: Path, out: Path, *, part_bytes: int = PART_BYTES) -> Path:
    """Export only verified bundle members, splitting each into ordered hashed parts."""
    if not 1 <= part_bytes <= PART_BYTES:
        raise ValueError("part_bytes must be between 1 and 1 GiB")
    _destination(out)
    candidates, references = load_bundle(bundle)
    manifest = json.loads((bundle / "embedding_bundle.json").read_text())
    names = {"embedding_bundle.json", manifest["pool"]["file"]}
    names.update(p.name for p in (*candidates.values(), *references.values()))
    if "preparation" in manifest:
        names.add(manifest["preparation"]["file"])
    records = []
    with tempfile.TemporaryDirectory(dir=out.parent) as temporary:
        stage = Path(temporary) / "assets"
        stage.mkdir()
        for index, name in enumerate(sorted(names)):
            source = bundle / _plain(name)
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"missing or symlinked bundle file: {name}")
            parts = []
            original = hashlib.sha256()
            total = 0
            with source.open("rb") as stream:
                while True:
                    block = stream.read(min(BLOCK_BYTES, part_bytes))
                    if not block:
                        break
                    filename = f"asset-{index:04d}-{len(parts):06d}.part"
                    digest = hashlib.sha256()
                    size = 0
                    with (stage / filename).open("xb") as target:
                        while block:
                            target.write(block)
                            digest.update(block)
                            original.update(block)
                            size += len(block)
                            total += len(block)
                            if size == part_bytes:
                                break
                            block = stream.read(min(BLOCK_BYTES, part_bytes - size))
                    parts.append({"file": filename, "sha256": digest.hexdigest(), "size": size})
            records.append(
                {"file": name, "sha256": original.hexdigest(), "size": total, "parts": parts}
            )
        (stage / MANIFEST).write_text(json.dumps({"schema_version": 1, "files": records}) + "\n")
        _destination(out)
        stage.rename(out)
    return out


def restore(directory: Path, out: Path) -> Path:
    """Verify parts and original hashes, then atomically expose a verified bundle."""
    _destination(out)
    manifest_path = directory / MANIFEST
    if manifest_path.is_symlink():
        raise ValueError("transport manifest must not be a symlink")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("unsupported transport manifest")
    names, used_parts = set(), set()
    with tempfile.TemporaryDirectory(dir=out.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        for record in manifest["files"]:
            name = _plain(record["file"])
            if name in names:
                raise ValueError("duplicate transport destination")
            names.add(name)
            target = stage / name
            with target.open("xb") as stream:
                for part in record["parts"]:
                    filename = _plain(part["file"])
                    source = directory / filename
                    if filename in used_parts or source.is_symlink() or not source.is_file():
                        raise ValueError(
                            f"missing, duplicate or symlinked transport part: {filename}"
                        )
                    used_parts.add(filename)
                    if (
                        source.stat().st_size != part["size"]
                        or sha256_file(source) != part["sha256"]
                    ):
                        raise ValueError(f"transport part checksum or size mismatch: {filename}")
                    with source.open("rb") as reader:
                        shutil.copyfileobj(reader, stream, length=BLOCK_BYTES)
            if target.stat().st_size != record["size"] or sha256_file(target) != record["sha256"]:
                raise ValueError(f"reassembled file checksum or size mismatch: {name}")
        load_bundle(stage)
        _destination(out)
        stage.rename(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("stage-release")
    export.add_argument("--bundle", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    unpack = commands.add_parser("restore")
    unpack.add_argument("--directory", type=Path, required=True)
    unpack.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "stage-release":
            stage_release(args.bundle, args.out)
        else:
            restore(args.directory, args.out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"bundle transport: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
