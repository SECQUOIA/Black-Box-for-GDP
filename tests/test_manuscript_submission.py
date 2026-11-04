"""Submission packaging checks use synthetic sources and need no TeX install."""

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_manuscript", ROOT / "scripts/build_manuscript.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture
def source(tmp_path):
    source = tmp_path / "manuscript"
    (source / "shared").mkdir(parents=True)
    (source / "figures").mkdir()
    (source / "arxiv.tex").write_text("\\input{main.tex}\n")
    (source / "cace.tex").write_text("\\def\\cacesubmission{}\\input{main.tex}\n")
    (source / "main.tex").write_text(
        "% \\input{private.tex}\n"
        "\\input{shared/body}\n"
        "\\bibliographystyle{elsarticle-harv}\n"
        "\\bibliography{reference}\n"
        "\\input{supplementary}\n"
    )
    (source / "shared/body.tex").write_text(
        "Retained bytes: 20\\% and text.\n"
        "20\\% % \\input{private-after-percent.tex}\n"
        "\\includegraphics*[width=\\linewidth]{figures/figure.pdf}\n"
    )
    (source / "supplementary.tex").write_text(
        "\\bibliographystyle{elsarticle-harv}\n\\bibliography{reference}\n"
    )
    (source / "reference.bib").write_text("@article{example,title={Example}}\n")
    (source / "elsarticle-harv.bst").write_text("bibliography style fixture\n")
    (source / "figures/figure.pdf").write_bytes(b"%PDF-1.4 referenced figure\n")
    (source / "private.tex").write_text("private author notes\n")
    (source / ".env").write_text("SECRET=excluded\n")
    (source / "unrelated.zip").write_bytes(b"not manuscript input\n")
    return source


def test_recursive_flat_bundle_has_only_declared_inputs(source):
    members, inventory, _ = builder.collect_sources(source)
    assert set(members) == {
        *builder.ENTRYPOINTS, "body.tex", "figure.pdf", "reference.bib",
        "elsarticle-harv.bst",
    }
    assert all(Path(name).name == name for name in members)
    assert members["arxiv.tex"] == (source / "arxiv.tex").read_bytes()
    assert members["reference.bib"] == (source / "reference.bib").read_bytes()
    assert members["figure.pdf"] == (source / "figures/figure.pdf").read_bytes()
    assert members["body.tex"] == (
        source / "shared/body.tex"
    ).read_bytes().replace(b"figures/figure.pdf", b"figure.pdf")
    assert b"\\input{body}" in members["main.tex"]
    assert b"% \\input{private.tex}" in members["main.tex"]
    assert next(row for row in inventory if row["member"] == "body.tex")[
        "source"
    ] == "shared/body.tex"


def test_missing_input_preserves_previous_output(source, tmp_path):
    output = tmp_path / "previous-build"
    output.mkdir()
    marker = output / "arxiv.pdf"
    marker.write_bytes(b"previous verified artifact")
    (source / "figures/figure.pdf").unlink()
    with pytest.raises(builder.BuildError, match="Missing manuscript input"):
        builder.build_submission(source, output)
    assert marker.read_bytes() == b"previous verified artifact"
    assert list(output.iterdir()) == [marker]
    fresh = tmp_path / "fresh-build"
    with pytest.raises(builder.BuildError, match="Missing manuscript input"):
        builder.build_submission(source, fresh)
    assert not fresh.exists()


def test_output_safety_rejects_source_ancestors_symlinks_and_existing(source, tmp_path):
    _, _, inputs = builder.collect_sources(source)
    for output in (source, source.parent, source / "build"):
        with pytest.raises(builder.BuildError, match="Unsafe output"):
            builder.validate_output(output, source, inputs)
    alias = tmp_path / "source-alias"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(builder.BuildError, match="Unsafe output"):
        builder.validate_output(alias, source, inputs)
    previous = tmp_path / "previous"
    previous.mkdir()
    with pytest.raises(builder.BuildError, match="existing output is preserved"):
        builder.validate_output(previous, source, inputs)
    with pytest.raises(builder.BuildError, match="absolute path"):
        builder.validate_output(Path("relative-build"), source, inputs)


def test_dependencies_cannot_escape_or_add_non_manuscript_inputs(source, tmp_path):
    outside = tmp_path / "private.tex"
    outside.write_text("not a manuscript input")
    (source / "main.tex").write_text("\\input{../private.tex}\n")
    with pytest.raises(builder.BuildError, match="leaves manuscript"):
        builder.collect_sources(source)
    (source / "main.tex").write_text("\\input{.env}\n")
    with pytest.raises(builder.BuildError, match="Unsupported manuscript input type"):
        builder.collect_sources(source)
    (source / "main.tex").write_text("\\input{linked.tex}\n")
    (source / "linked.tex").symlink_to(outside)
    with pytest.raises(builder.BuildError, match="leaves manuscript"):
        builder.collect_sources(source)


def test_flattening_rejects_colliding_basenames(source):
    (source / "body.tex").write_text("a different input")
    with (source / "main.tex").open("a") as handle:
        handle.write("\\input{body.tex}\n")
    with pytest.raises(builder.BuildError, match="filename collision"):
        builder.collect_sources(source)


def test_unbraced_static_input_is_resolved_and_dynamic_syntax_rejected(source):
    main = source / "main.tex"
    main.write_text("\\input shared/body.tex\n")
    members, _, _ = builder.collect_sources(source)
    assert members["main.tex"] == b"\\input body.tex\n"
    main.write_text("\\input{\\dynamic{nested}}\n")
    with pytest.raises(builder.BuildError, match="Unsupported dependency syntax"):
        builder.collect_sources(source)


@pytest.mark.parametrize("target", ["arxiv", "cace", "all"])
def test_build_packages_selected_targets_and_records_hashes(source, tmp_path, monkeypatch, target):
    compiled = []
    monkeypatch.setattr(builder.shutil, "which", lambda name: f"/test/{name}")

    def compile_fixture(stem, working, logs, tools, commands):
        compiled.append(stem)
        for suffix in ("pdf", "aux", "bbl"):
            (working / f"{stem}.{suffix}").write_text(f"built {stem}.{suffix}\n")

    monkeypatch.setattr(builder, "compile_document", compile_fixture)
    output = tmp_path / f"build-{target}"
    builder.build_submission(source, output, target)
    selected = ["arxiv", "cace"] if target == "all" else [target]
    assert compiled == ["supplementary", *selected]
    assert set(path.name for path in output.glob("*.pdf")) == {
        "supplementary.pdf", *(f"{stem}.pdf" for stem in selected)
    }
    manifest = json.loads((output / "manifest.json").read_text())
    for name, evidence in manifest["artifacts"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == evidence["sha256"]
    for stem in selected:
        with zipfile.ZipFile(output / f"{stem}_sources.zip") as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            assert all(Path(name).name == name for name in names)
            assert not {"private.tex", ".env", "unrelated.zip"} & set(names)
            assert {"main.tex", "supplementary.tex"} <= set(names)
            assert not {"arxiv.tex", "cace.tex", "arxiv.bbl", "cace.bbl"} & set(names)
            assert archive.read("main.bbl") == f"built {stem}.bbl\n".encode()
            prefix = b"\\def\\cacesubmission{1}\n" if stem == "cace" else b""
            assert archive.read("main.tex") == prefix + builder.collect_sources(source)[0]["main.tex"]
            assert archive.read("figure.pdf") == (source / "figures/figure.pdf").read_bytes()
            assert {"main.bbl", "supplementary.bbl"} <= set(names)
            assert ("supplementary.aux" in names) == (stem == "cace")
            assert ("supplementary.pdf" in names) == (stem == "cace")
            description = manifest["archives"][f"{stem}_sources.zip"]
            assert description["master"] == "main.tex"
            assert description["target"] == stem
            assert description["target_prefix"] == prefix.decode()
            assert description["members"] == {
                name: hashlib.sha256(archive.read(name)).hexdigest() for name in names
            }


def test_final_undefined_citations_fail_build_and_keep_logs(tmp_path, monkeypatch):
    working, logs = tmp_path / "manuscript", tmp_path / "logs"
    working.mkdir()
    logs.mkdir()

    def fake_run(command, cwd, logfile, commands):
        logfile.write_text("retained subprocess log\n")
        if command[0] == "pdflatex":
            (cwd / "arxiv.log").write_text(
                "Package natbib Warning: There were undefined citations.\n"
            )

    monkeypatch.setattr(builder, "_run_command", fake_run)
    with pytest.raises(builder.BuildError, match="Unresolved references/citations"):
        builder.compile_document("arxiv", working, logs,
                                 {"pdflatex": "pdflatex", "bibtex": "bibtex"}, [])
    assert (logs / "arxiv-pdflatex-5.log").is_file()
