"""Build a deterministic, pinned companion ZIP or verify its extracted contents.

Every committed file and exact pinned submodule revision is packaged, including
manuscript attachments and open-source license notices. Untracked local files
are excluded. Known private solver-license paths are rejected before ZIP creation.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile

from common import ROOT, read_json, sha, write_json


PRIVATE_SOLVER_LICENSE_NAMES = {"gamslice.dat", "gamslice.txt", "bamlice.txt"}
REMOVED_PRIVATE_ARCHIVE = "results/archives/gdpopt_baron_highs_20261001_partial.tar.gz"


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd)


def preflight_publication_paths(repo, revision, prefix=""):
    """Reject known private paths in the committed tree and pinned submodules."""
    for entry in git("ls-tree", "-rz", revision, cwd=repo).decode().split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        _, kind, commit = metadata.split()
        path = prefix + name
        if (
            PurePosixPath(path).name.lower() in PRIVATE_SOLVER_LICENSE_NAMES
            or path == REMOVED_PRIVATE_ARCHIVE
            or path.endswith("/" + REMOVED_PRIVATE_ARCHIVE)
        ):
            raise ValueError(
                f"Private solver-license artifact cannot be packaged: {path}; "
                "use the sanitized publication revision described in "
                "docs/publication_sanitization.md"
            )
        if kind == "commit":
            sub = repo / name
            if not (sub / ".git").exists():
                raise ValueError(f"Initialize pinned submodule first: {path}")
            preflight_publication_paths(sub, commit, path + "/")


def revision_files(repo, revision, prefix=""):
    """Stream the committed tree, expanding submodules at their recorded commits."""
    archive = git("archive", "--format=tar", revision, cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            if member.isfile():
                yield prefix + member.name, tar.extractfile(member).read(), member.mode
            elif member.issym() or member.islnk():
                raise ValueError(
                    f"Symlink must be reviewed before packaging: {member.name}"
                )
    for line in git("ls-tree", "-r", revision, cwd=repo).decode().splitlines():
        metadata, name = line.split("\t", 1)
        mode, kind, commit = metadata.split()
        if kind == "commit":
            sub = repo / name
            if not (sub / ".git").exists():
                raise ValueError(f"Initialize pinned submodule first: {name}")
            yield from revision_files(sub, commit, prefix + name + "/")


def build(revision, output):
    commit = git("rev-parse", "--verify", revision + "^{commit}").decode().strip()
    if output.exists() or output.with_suffix(".zip.sha256").exists():
        raise ValueError("Refusing to overwrite an existing release candidate")
    preflight_publication_paths(ROOT, commit)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, data, mode in sorted(revision_files(ROOT, commit)):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
            records.append(
                dict(path=name, sha256=hashlib.sha256(data).hexdigest(), size=len(data))
            )
        manifest = {
            "provider_revision": commit,
            "scope": "Exact repository commit plus exact pinned submodules; historical records unchanged",
            "submodules": {
                line.split("\t", 1)[1]: line.split()[2]
                for line in git("ls-tree", "-r", commit).decode().splitlines()
                if line.startswith("160000 ")
            },
            "public_release_status": "candidate_not_published",
            "files": records,
        }
        info = zipfile.ZipInfo("PACKAGE_MANIFEST.json", (1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps(manifest, indent=2) + "\n")
    digest = sha(output)
    output.with_suffix(".zip.sha256").write_text(digest + "  " + output.name + "\n")
    write_json(
        output.with_suffix(".package.json"),
        dict(
            provider_revision=commit,
            sha256=digest,
            files=len(records),
            size=output.stat().st_size,
            immutable_download_url=None,
            public_access_verified=False,
        ),
    )
    print(f"{output}: {digest} ({len(records)} files)")


def verify(root):
    root = root.resolve()
    manifest = read_json(root / "PACKAGE_MANIFEST.json")
    names = set()
    for r in manifest["files"]:
        name = r["path"]
        if (
            name in names
            or PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
        ):
            raise ValueError(f"Invalid or duplicate member: {name}")
        names.add(name)
        p = root / name
        if (
            not p.resolve().is_relative_to(root)
            or not p.is_file()
            or sha(p) != r["sha256"]
            or p.stat().st_size != r["size"]
        ):
            raise ValueError(f"Package file missing or modified: {name}")
    print(f"Verified {len(names)} files at {manifest['provider_revision']}")
    return len(names)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("build")
    b.add_argument(
        "--revision",
        required=True,
        help="Full commit SHA or tag resolved and recorded in manifest",
    )
    b.add_argument("--output", type=Path, required=True)
    v = commands.add_parser("verify")
    v.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.command == "build":
        build(args.revision, args.output.resolve())
    else:
        verify(args.root)
