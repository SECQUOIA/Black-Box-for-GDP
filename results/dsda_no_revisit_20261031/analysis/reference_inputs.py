"""Read exact, hash-verified reference bytes from existing Git objects."""

from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

RESULT = Path(__file__).resolve().parents[1]
REPOSITORY = RESULT.parents[1]
PROVENANCE = json.loads((RESULT / "PROVENANCE.json").read_text())


@lru_cache(maxsize=None)
def git_bytes(revision, path):
    return subprocess.check_output(
        ["git", "-C", str(REPOSITORY), "show", revision + ":" + path]
    )


@lru_cache(maxsize=None)
def reference_bytes(name):
    info = PROVENANCE[name]
    if "source_path" in info:
        data = git_bytes(info["revision"], info["source_path"])
    else:
        parent = git_bytes(
            info["parent_container_revision"], info["parent_archive_path"]
        )
        if hashlib.sha256(parent).hexdigest() != info["parent_archive_sha256"]:
            raise ValueError("Historical return SHA256 differs")
        with zipfile.ZipFile(io.BytesIO(parent)) as archive:
            if archive.testzip() is not None:
                raise ValueError("Historical return CRC failure")
            data = archive.read(info["source_member"])
    if hashlib.sha256(data).hexdigest() != info["sha256"]:
        raise ValueError("Reference/source hash differs: " + name)
    return data
