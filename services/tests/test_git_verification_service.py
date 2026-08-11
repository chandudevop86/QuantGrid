from __future__ import annotations

import subprocess

import pytest

from Backend.application.git_verification_service import GitVerificationError, GitVerificationService


def _git(repo, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "governance@example.test")
    _git(tmp_path, "config", "user.name", "Governance Test")
    (tmp_path / "requirements.txt").write_text("sqlalchemy==2.0.0\n", encoding="utf-8")
    (tmp_path / "strategy.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def test_capture_uses_actual_clean_head_and_is_deterministic(repository):
    service = GitVerificationService(repository)
    first = service.capture()
    second = service.capture(requested_commit_sha=first.head_commit_sha)

    assert first.git_is_clean is True
    assert first.reproducibility_status == "REPRODUCIBLE"
    assert first.code_snapshot_hash == second.code_snapshot_hash
    assert first.dependency_lock_hash == second.dependency_lock_hash


def test_capture_marks_dirty_repository_non_reproducible(repository):
    (repository / "strategy.py").write_text("VALUE = 2\n", encoding="utf-8")

    provenance = GitVerificationService(repository).capture()

    assert provenance.git_is_clean is False
    assert provenance.reproducibility_status == "NON_REPRODUCIBLE"


def test_capture_rejects_requested_commit_that_is_not_actual_head(repository):
    requested_commit = _git(repository, "rev-parse", "HEAD")
    _git(repository, "commit", "--allow-empty", "-m", "later head")

    with pytest.raises(GitVerificationError, match="not the actual executing HEAD"):
        GitVerificationService(repository).capture(requested_commit_sha=requested_commit)
