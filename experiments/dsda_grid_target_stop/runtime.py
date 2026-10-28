"""Retained repository identity and solver/process guards from the baseline runner."""

import hashlib
import importlib.abc
from pathlib import Path
import subprocess
import sys

THREADS = {
    k: "1"
    for k in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "GOTO_NUM_THREADS",
        "NUMEXPR_MAX_THREADS",
    )
}


def verify_repository(repo):
    """Identify the project by retained Git history, including renamed forks."""
    repo = Path(repo).resolve()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True
        )

    top = git("rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != repo:
        raise ValueError("Expected an existing repository root: " + str(repo))
    head = git("rev-parse", "HEAD")
    if head.returncode:
        raise ValueError("Cannot read repository HEAD")
    anchor = "eeb560059c7001ad82c13b9249168531af073f95"
    ancestry = git("merge-base", "--is-ancestor", anchor, "HEAD")
    if ancestry.returncode:
        raise ValueError(
            "Repository does not contain the adopted Grid execution revision in its HEAD history: "
            + anchor
        )
    frozen = git("show", anchor + ":grid_dsda.py")
    expected = "7873a2344eb9b40e9bc3f35354448494e9d8230d0879377e8934fa2cc517a77a"
    if (
        frozen.returncode
        or hashlib.sha256(frozen.stdout.encode()).hexdigest() != expected
    ):
        raise ValueError("Repository historical D-SDA source fingerprint mismatch")
    remotes = {}
    names = git("remote")
    if names.returncode:
        raise ValueError("Cannot inspect repository remotes")
    from urllib.parse import urlsplit, urlunsplit

    for name in names.stdout.splitlines():
        value = git("remote", "get-url", name)
        if value.returncode:
            raise ValueError("Cannot inspect remote " + name)
        url = value.stdout.strip()
        if "://" in url:
            parsed = urlsplit(url)
            # Credentials are not needed for repository identity or provenance.
            host = parsed.hostname or ""
            if parsed.port:
                host += ":" + str(parsed.port)
            url = urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        remotes[name] = url
    return dict(
        repository=str(repo),
        head=head.stdout.strip(),
        remotes=remotes,
        verified_ancestor=anchor,
        verified_ancestor_dsda_sha256=expected,
        rule="Exact retained execution commit is an ancestor of HEAD and its D-SDA source hash matches; remote URLs are recorded, not required to use the latest repository name.",
    )


BLOCKED = []


class SolverBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "pyomo",
            "gams",
            "pyscipopt",
            "gdp",
            "gdp_models",
            "rbfopt",
            "bam",
            "fmqa_benchmark",
            "case_studies",
            "cyipopt",
        }:
            BLOCKED.append("import:" + fullname)
            raise RuntimeError(
                "Solver/model/other-method import prohibited: " + fullname
            )


def install_no_solver_guard():
    if any(isinstance(f, SolverBlocker) for f in sys.meta_path):
        return
    sys.meta_path.insert(0, SolverBlocker())

    def audit(event, args):
        if event in {
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
            "os.exec",
            "os.fork",
            "os.forkpty",
        }:
            BLOCKED.append(event)
            raise RuntimeError(
                "Child process creation prohibited inside lookup worker: " + event
            )

    sys.addaudithook(audit)


THREADS.update(
    OMP_DYNAMIC="FALSE",
    MKL_DYNAMIC="FALSE",
    CUDA_VISIBLE_DEVICES="",
    PYTHONNOUSERSITE="1",
)
