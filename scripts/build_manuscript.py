#!/usr/bin/env python3
"""Build fresh, flat manuscript submissions using Python's standard library.

Requires pdflatex, bibtex, and elsarticle-harv.bst (via --bst or kpsewhich).
The required --output directory must be new; source files are never overwritten.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import zipfile


ENTRYPOINTS = ("arxiv.tex", "cace.tex", "main.tex", "supplementary.tex")
GRAPHICS = (".pdf", ".png", ".jpg", ".jpeg", ".eps")
COMMAND = r"\\(input|include|includegraphics\*?|bibliography|bibliographystyle)(?![A-Za-z@])"
DEPENDENCY = re.compile(
    COMMAND + r"\s*(?:\[[^\]]*\]\s*)?(?:\{([^{}]*)\}|([^\s\\{}%]+))"
)
UNRESOLVED = re.compile(
    r"There were undefined (?:references|citations)|"
    r"(?:Citation|Reference)[^\n]*undefined", re.IGNORECASE
)
RERUN = re.compile(r"Rerun to get|Label\(s\) may have changed", re.IGNORECASE)
WALL_SECONDS = 180
MEMORY_BYTES = 2 * 1024**3


class BuildError(RuntimeError):
    """An input, toolchain, or compilation requirement was not met."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _without_comments(text):
    """Mask TeX comments while retaining source offsets for path replacement."""
    masked = list(text)
    for match in re.finditer("%", text):
        start = match.start()
        if masked[start] != "%":
            continue
        preceding = start
        while preceding and text[preceding - 1] == "\\":
            preceding -= 1
        if (start - preceding) % 2 == 0:
            end = text.find("\n", start)
            end = len(text) if end == -1 else end
            masked[start:end] = " " * (end - start)
    return "".join(masked)


def collect_sources(source, bst=None):
    """Resolve explicit dependencies within manuscript/, returning flat bytes.

    TeX resolves relative paths from its working directory, including paths in
    nested inputs. Only these declared files are copied, never a directory tree.
    """
    source = Path(source).resolve()
    members, originals, paths, pending = {}, {}, {}, []
    provided_bst = Path(bst).resolve() if bst is not None else None

    def add(path, member=None, external=False):
        path = path.resolve()
        if not external and not path.is_relative_to(source):
            raise BuildError(f"Dependency leaves manuscript directory: {path.name}")
        if not path.is_file():
            raise BuildError(f"Missing manuscript input: {path.name}")
        member = member or path.name
        for other, known_path in paths.items():
            if other.casefold() == member.casefold() and known_path != path:
                raise BuildError(f"Flat source filename collision: {member}")
        if member not in paths:
            data = path.read_bytes()
            paths[member] = path
            members[member] = originals[member] = data
            if path.suffix == ".tex":
                pending.append(member)
        return member

    def resolve(value, suffixes):
        if not value or re.search(r"[\\{}#$%\s]", value):
            raise BuildError(f"Only static manuscript paths are supported: {value!r}")
        token = Path(value)
        if token.is_absolute():
            raise BuildError(f"Absolute manuscript dependency is unsupported: {value}")
        if any(part.startswith(".") and part not in (".", "..") for part in token.parts):
            raise BuildError(f"Unsupported manuscript input type: {value}")
        candidates = [source / token] if token.suffix else [
            source / f"{value}{suffix}" for suffix in suffixes
        ]
        if token.suffix and token.suffix.lower() not in suffixes:
            raise BuildError(f"Unsupported manuscript input type: {value}")
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise BuildError(f"Missing manuscript input: {value}")

    for entrypoint in ENTRYPOINTS:
        add(source / entrypoint)
    while pending:
        member = pending.pop()
        text = originals[member].decode("utf-8")
        masked = _without_comments(text)
        matches = list(DEPENDENCY.finditer(masked))
        if {match.start() for match in re.finditer(COMMAND, masked)} != {
            match.start() for match in matches
        }:
            raise BuildError(f"Unsupported dependency syntax in {member}")
        replacements = []
        for match in matches:
            command = match.group(1)
            value_group = 2 if match.group(2) is not None else 3
            if value_group == 3 and command != "input":
                raise BuildError(f"Expected a braced dependency in {member}")
            raw = match.group(value_group)
            values = raw.split(",") if command == "bibliography" else [raw]
            flattened = []
            for token in values:
                value = token.strip()
                if command == "bibliographystyle":
                    if value != "elsarticle-harv":
                        raise BuildError(f"Unsupported bibliography style: {value}")
                    path = provided_bst or source / f"{value}.bst"
                    if not path.is_file() and provided_bst is None:
                        kpsewhich = shutil.which("kpsewhich")
                        found = subprocess.run(
                            [kpsewhich, f"{value}.bst"], capture_output=True,
                            text=True, timeout=15, check=False,
                        ) if kpsewhich else None
                        if found and found.returncode == 0 and found.stdout.strip():
                            path = Path(found.stdout.strip())
                    if not path.is_file():
                        raise BuildError("Missing elsarticle-harv.bst; supply --bst PATH")
                    add(path, f"{value}.bst", external=True)
                    flattened.append(token)
                    continue
                suffixes = GRAPHICS if command.startswith("includegraphics") else (
                    (".bib",) if command == "bibliography" else (".tex",)
                )
                path = resolve(value, suffixes)
                name = add(path)
                flat_name = name if Path(value).suffix else Path(name).stem
                flattened.append(token.replace(value, flat_name, 1))
            replacement = ",".join(flattened)
            if replacement != raw:
                replacements.append((match.start(value_group), match.end(value_group), replacement))
        for start, end, replacement in reversed(replacements):
            text = text[:start] + replacement + text[end:]
        members[member] = text.encode("utf-8")

    inventory = []
    for member in sorted(members):
        path = paths[member]
        origin = str(path.relative_to(source)) if path.is_relative_to(source) else (
            "provided bibliography style"
        )
        inventory.append({"source": origin, "member": member,
                          "sha256": digest(originals[member]),
                          "staged_sha256": digest(members[member])})
    return members, inventory, set(paths.values())


def validate_output(output, source, inputs):
    output, source = Path(output), Path(source).resolve()
    if not output.is_absolute():
        raise BuildError("--output must be an absolute path")
    resolved = output.resolve()
    if (resolved == source or resolved in source.parents
            or resolved.is_relative_to(source)
            or any(path.is_relative_to(resolved) for path in inputs)):
        raise BuildError("Unsafe output: choose a directory outside manuscript and its inputs")
    if output.exists() or output.is_symlink():
        raise BuildError("Output must be a new directory; existing output is preserved")
    return resolved


def _resource_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _run_command(command, working, logfile, commands):
    commands.append({"argv": [Path(command[0]).name, *command[1:]],
                     "cwd": "manuscript", "log": f"logs/{logfile.name}"})
    env = os.environ.copy()
    env.update({"openin_any": "p", "openout_any": "p", "shell_escape": "f"})
    with logfile.open("wb") as log:
        try:
            process = subprocess.Popen(
                command, cwd=working, stdout=log, stderr=subprocess.STDOUT,
                env=env, preexec_fn=_resource_limits, start_new_session=True,
            )
            try:
                result = process.wait(timeout=WALL_SECONDS)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise BuildError(f"Build timed out; see {logfile}") from exc
        except OSError as exc:
            raise BuildError(f"Cannot run {command[0]}; see {logfile}: {exc}") from exc
    if result:
        raise BuildError(f"{Path(command[0]).name} failed ({result}); see {logfile}")


def compile_document(stem, working, logs, tools, commands):
    def latex(pass_number):
        _run_command([
            tools["pdflatex"], "-no-shell-escape", "-interaction=nonstopmode",
            "-halt-on-error", "-file-line-error", f"{stem}.tex",
        ], working, logs / f"{stem}-pdflatex-{pass_number}.log", commands)
        log = working / f"{stem}.log"
        if not log.is_file():
            raise BuildError(f"pdflatex did not produce {stem}.log")
        return log.read_text(errors="replace")

    latex(1)
    _run_command([tools["bibtex"], stem], working,
                 logs / f"{stem}-bibtex.log", commands)
    for pass_number in range(2, 6):
        final_log = latex(pass_number)
        if pass_number >= 3 and not (UNRESOLVED.search(final_log) or RERUN.search(final_log)):
            break
    if UNRESOLVED.search(final_log) or RERUN.search(final_log):
        raise BuildError(f"Unresolved references/citations in final {stem}.log")
    for suffix in (".pdf", ".aux", ".bbl"):
        if not (working / f"{stem}{suffix}").is_file():
            raise BuildError(f"Build did not produce {stem}{suffix}")


def write_archive(path, members):
    """Use stable metadata and flat, duplicate-free source members."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def submission_sources(stem, members, working):
    """Give submission portals one conventional main.tex and matching BBL."""
    packaged = {name: data for name, data in members.items()
                if name not in ("arxiv.tex", "cace.tex")}
    prefix = "\\def\\cacesubmission{1}\n" if stem == "cace" else ""
    packaged["main.tex"] = prefix.encode() + packaged["main.tex"]
    packaged["main.bbl"] = (working / f"{stem}.bbl").read_bytes()
    extras = ["supplementary.bbl"]
    if stem == "cace":
        # xr-hyper reads the auxiliary labels and links to this sibling PDF.
        extras += ["supplementary.aux", "supplementary.pdf"]
    packaged.update({name: (working / name).read_bytes() for name in extras})
    return packaged, {"master": "main.tex", "target": stem, "target_prefix": prefix,
                      "members": {name: digest(data) for name, data in sorted(packaged.items())}}


def build_submission(source, output, target="all", bst=None):
    if target not in ("all", "arxiv", "cace"):
        raise BuildError(f"Unknown submission target: {target}")
    members, inventory, inputs = collect_sources(source, bst)
    output = validate_output(output, source, inputs)
    tools = {name: shutil.which(name) for name in ("pdflatex", "bibtex")}
    if not all(tools.values()):
        raise BuildError("pdflatex and bibtex must be installed and available on PATH")
    output.mkdir(parents=True)
    working, logs = output / "manuscript", output / "logs"
    working.mkdir()
    logs.mkdir()
    for name, data in members.items():
        (working / name).write_bytes(data)
    selected = ("arxiv", "cace") if target == "all" else (target,)
    commands = []
    archives = {}
    compile_document("supplementary", working, logs, tools, commands)
    artifacts = ["supplementary.pdf"]
    for stem in selected:
        compile_document(stem, working, logs, tools, commands)
        artifacts.append(f"{stem}.pdf")
        source_members, archive_manifest = submission_sources(stem, members, working)
        archive_name = f"{stem}_sources.zip"
        write_archive(output / archive_name, source_members)
        archives[archive_name] = archive_manifest
        artifacts.append(archive_name)
    for name in artifacts:
        if name.endswith(".pdf"):
            shutil.copyfile(working / name, output / name)
    manifest = {
        "target": target, "entrypoints": [f"{stem}.tex" for stem in selected],
        "inputs": inventory, "commands": commands, "archives": archives,
        "limits": {"wall_seconds_per_command": WALL_SECONDS,
                   "address_space_bytes": MEMORY_BYTES, "cpu_seconds": 120},
        "artifacts": {name: {"sha256": digest((output / name).read_bytes()),
                             "bytes": (output / name).stat().st_size}
                      for name in artifacts},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("arxiv", "cace", "all"), default="all")
    parser.add_argument("--output", required=True, type=Path,
                        help="absolute path to a new, disposable build directory")
    parser.add_argument("--bst", type=Path, help="explicit elsarticle-harv.bst file")
    args = parser.parse_args(argv)
    try:
        result = build_submission(Path(__file__).resolve().parents[1] / "manuscript",
                                  args.output, args.target, args.bst)
    except (BuildError, OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        print(f"Manuscript build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Built {args.target} submission in {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
