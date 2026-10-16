"""Verify and access immutable benchmark ZIPs without running archived code."""

import argparse
from contextlib import contextmanager
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "results/archives/catalog.json"


def datasets():
    catalog = json.loads(CATALOG.read_text())
    if catalog["schema"] != 1:
        raise ValueError("Unsupported archive catalog schema")
    return catalog["datasets"]


def entry_for_path(path):
    """Recognize retained summary directories and their original ZIPs."""
    path = Path(path).resolve()
    for entry in datasets().values():
        if path in {(ROOT / entry[key]).resolve() for key in ("directory", "archive")}:
            return entry
    return None


@contextmanager
def verified_zip(entry):
    path = ROOT / entry["archive"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError(f"Archive checksum mismatch: {path}")
    prefix = entry["archive_root"] + "/"
    with zipfile.ZipFile(path) as archive:
        names = set()
        for member in archive.infolist():
            name = PurePosixPath(member.filename)
            if (member.filename in names or not member.filename.startswith(prefix)
                    or name.is_absolute() or ".." in name.parts
                    or "\\" in member.filename or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError(f"Unsafe or duplicate archive member: {member.filename}")
            names.add(member.filename)
        files = {m.filename[len(prefix):] for m in archive.infolist() if not m.is_dir()}
        hashes = {}
        for line in archive.read(prefix + "SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            if name in hashes:
                raise ValueError(f"Duplicate checksum entry: {name}")
            hashes[name] = digest
        if files != set(hashes) | {"SHA256SUMS"}:
            raise ValueError("Incomplete archive checksum inventory")
        for name, digest in hashes.items():
            if hashlib.sha256(archive.read(prefix + name)).hexdigest() != digest:
                raise ValueError(f"Internal checksum mismatch: {name}")
        for section in entry["archived_only"]:
            if section["directory"] == "trajectories" and "trace_index" in entry:
                raw = (ROOT / entry["directory"] / entry["trace_index"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry["trace_index_sha256"]:
                    raise ValueError("Trajectory index checksum mismatch")
                rows = list(csv.DictReader(io.StringIO(raw.decode())))
                if len({r["archive_trace_path"] for r in rows}) != len(rows):
                    raise ValueError("Duplicate indexed trajectory")
                for row in rows:
                    if hashes.get(row["archive_trace_path"]) != row["trajectory_sha256"]:
                        raise ValueError("Indexed trajectory differs from archive")
                count = len(rows)
            else:
                count = sum(n.startswith(section["directory"] + "/") for n in files)
            if count != section["files"]:
                raise ValueError(f"Archived file count differs: {section['directory']}")
        yield archive, len(hashes)


@contextmanager
def archived_directory(path):
    """Use a verified temporary extraction for registered result locations."""
    path = Path(path)
    entry = entry_for_path(path)
    if entry is None:
        yield path
        return
    with verified_zip(entry) as (archive, _), tempfile.TemporaryDirectory(prefix="benchmark-archive-") as temp:
        archive.extractall(temp)
        yield Path(temp) / entry["archive_root"]


def extract(entry, output):
    """Extract only after verification, into a new directory; never overwrite."""
    output = Path(output)
    with verified_zip(entry) as (archive, _):
        output.mkdir(parents=True, exist_ok=False)
        archive.extractall(output)
    return output / entry["archive_root"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "extract"))
    parser.add_argument("datasets", nargs="*", help="Catalog keys; verify defaults to all")
    parser.add_argument("--output", type=Path, help="New extraction directory")
    args = parser.parse_args()
    entries = datasets()
    selected = args.datasets or list(entries)
    if set(selected) - set(entries):
        parser.error("Unknown dataset; choose from " + ", ".join(entries))
    if args.action == "extract":
        if len(selected) != 1 or args.output is None:
            parser.error("extract requires one dataset and --output")
        print(extract(entries[selected[0]], args.output))
    else:
        if args.output is not None:
            parser.error("--output is only used with extract")
        for name in selected:
            entry = entries[name]
            with verified_zip(entry) as (_, count):
                print(json.dumps({"dataset": name, "status": "PASS", "archive": entry["archive"],
                                  "sha256": entry["sha256"], "verified_files": count,
                                  "archived_only_files": sum(s["files"] for s in entry["archived_only"])}))


if __name__ == "__main__":
    main()
