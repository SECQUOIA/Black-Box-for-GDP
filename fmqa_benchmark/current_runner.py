"""Route public FMQA entry points to the frozen QHD PyTorch experiment."""

import sys


def translate_arguments(argv):
    args = list(argv)
    scope = "process"
    if "--dataset" in args:
        index = args.index("--dataset")
        value = args[index + 1]
        if value not in ("case", "grid"):
            raise ValueError("--dataset must be case or grid")
        scope = "process" if value == "case" else "grid"
        del args[index:index + 2]
    if "--scope" not in args:
        args += ["--scope", scope]
    if "--resume" in args:
        index = args.index("--resume")
        args[index] = "--run-dir"
        args[0] = "resume"
    if "--experiment" in args:
        raise ValueError("FMQA entry points always use the QHD experiment")
    if "--output-root" not in args:
        from fmqa_benchmark.publication import ROOT
        args += ["--output-root", str(ROOT / "results/fmqa_qhd")]
    if "--fmqa-python" not in args:
        args += ["--fmqa-python", sys.executable]
    return args + ["--experiment", "fmqa_qhd"]


def main(argv=None):
    from process_followup_runner import main as run
    return run(translate_arguments(sys.argv[1:] if argv is None else argv))
