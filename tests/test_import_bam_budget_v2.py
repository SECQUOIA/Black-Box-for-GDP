"""Integration checks against the exact returned BAM batches, without solvers."""
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import import_bam_budget_v2 as importer  # noqa: E402 -- repository path is established above

@pytest.mark.parametrize('kind', ['cstr','non_cstr'])
def test_pinned_batch_and_all_terminal_returns(kind, tmp_path):
    name, digest, package_digest, count = importer.BATCHES[kind]
    audit = importer.verify_batch(kind, ROOT/'results/archives'/(name+'.zip'), tmp_path/'verified')
    assert audit['slots'] == count
    assert sum(audit['categories'].values()) == count
    assert audit['budget_overruns'] == audit['undelivered_terminal_values'] == 0
    assert audit['callbacks'] == (1530 if kind == 'cstr' else 1900)

@pytest.mark.parametrize('kind', ['cstr','non_cstr'])
def test_modified_return_is_rejected_before_extraction(kind, tmp_path):
    name = importer.BATCHES[kind][0]
    bad = tmp_path/(name+'.zip')
    bad.write_bytes((ROOT/'results/archives'/(name+'.zip')).read_bytes()+b'changed')
    with pytest.raises(ValueError, match='Unexpected return archive hash'):
        importer.verify_batch(kind, bad, tmp_path/'output')
    assert not (tmp_path/'output').exists()
