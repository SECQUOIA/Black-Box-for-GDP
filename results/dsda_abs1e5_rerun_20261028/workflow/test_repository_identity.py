"""Repository-name changes must not bypass or break history verification."""

import hashlib
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import run


class RepositoryIdentityTests(unittest.TestCase):
    def fake_git(self, command, **kwargs):
        args = command[3:]
        code = 0
        if args == ["rev-parse", "--show-toplevel"]:
            text = str(self.repo) + "\n"
        elif args == ["rev-parse", "HEAD"]:
            text = "a" * 40 + "\n"
        elif args[:2] == ["merge-base", "--is-ancestor"]:
            text = ""
            code = self.ancestry_code
        elif args[0] == "show":
            text = self.frozen
        elif args == ["remote"]:
            text = "origin\nupstream\n"
        elif args[:2] == ["remote", "get-url"]:
            text = self.remotes[args[2]] + "\n"
        else:
            raise AssertionError(command)
        return subprocess.CompletedProcess(command, code, text, "")

    def setUp(self):
        self.repo = Path("/tmp/dsda-repository-test").resolve()
        self.ancestry_code = 0
        self.frozen = (run.ROOT / "original/grid_dsda.py").read_text()
        self.remotes = {
            "origin": "git@github.com:AlbertLee125/RBFopt_Test.git",
            "upstream": "https://github.com/SECQUOIA/RBFopt_Test.git",
        }

    def test_historical_fork_and_renamed_upstream(self):
        with patch.object(run.subprocess, "run", self.fake_git):
            record = run.verify_repository(self.repo)
        self.assertEqual(record["remotes"], self.remotes)
        self.assertEqual(
            record["verified_ancestor_dsda_sha256"],
            hashlib.sha256(self.frozen.encode()).hexdigest(),
        )

    def test_custom_mirror_with_exact_history(self):
        self.remotes = {
            "origin": "/local/mirror/black_box.git",
            "upstream": "ssh://git@github-alias/SECQUOIA/Black-Box-for-GDP.git",
        }
        with patch.object(run.subprocess, "run", self.fake_git):
            run.verify_repository(self.repo)

    def test_wrong_history_rejected_even_with_expected_url(self):
        self.remotes["origin"] = "https://github.com/SECQUOIA/Black-Box-for-GDP.git"
        self.ancestry_code = 1
        with (
            patch.object(run.subprocess, "run", self.fake_git),
            self.assertRaisesRegex(ValueError, "HEAD history"),
        ):
            run.verify_repository(self.repo)

    def test_wrong_source_fingerprint_rejected(self):
        self.frozen += "\n# unexpected source\n"
        with (
            patch.object(run.subprocess, "run", self.fake_git),
            self.assertRaisesRegex(ValueError, "fingerprint"),
        ):
            run.verify_repository(self.repo)

    def test_url_credentials_omitted(self):
        self.remotes["origin"] = (
            "https://test_user:test_secret@github.com/AlbertLee125/RBFopt_Test.git?token=test_secret"
        )
        with patch.object(run.subprocess, "run", self.fake_git):
            record = run.verify_repository(self.repo)
        self.assertNotIn("test_secret", str(record))
        self.assertEqual(
            record["remotes"]["origin"],
            "https://github.com/AlbertLee125/RBFopt_Test.git",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
