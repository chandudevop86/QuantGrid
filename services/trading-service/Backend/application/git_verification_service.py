from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from Backend.domain.governance_models import canonical_json, sha256_text


class GitVerificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GitProvenance:
    repository_root: str
    head_commit_sha: str
    git_tree_hash: str
    git_is_clean: bool
    code_snapshot_hash: str
    dependency_lock_hash: str
    execution_environment_hash: str
    reproducibility_status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class GitVerificationService:
    """Captures the code and runtime that is actually executing a governed run."""

    _LOCK_FILENAMES = (
        "requirements.txt",
        "requirements-dev.txt",
        "poetry.lock",
        "Pipfile.lock",
        "uv.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    )

    def __init__(self, repository_root: str | Path | None = None) -> None:
        self.repository_root = Path(repository_root).resolve() if repository_root else self._discover_root()

    def capture(self, *, requested_commit_sha: str | None = None) -> GitProvenance:
        head = self._git("rev-parse", "HEAD")
        tree = self._git("rev-parse", "HEAD^{tree}")
        if requested_commit_sha:
            requested = self._git("rev-parse", "--verify", f"{requested_commit_sha}^{{commit}}")
            if requested != head:
                raise GitVerificationError(
                    f"Requested commit {requested} is not the actual executing HEAD {head}"
                )
        dirty = bool(self._git("status", "--porcelain=v1", "--untracked-files=all"))
        dependency_hash = self._dependency_lock_hash()
        code_hash = self._code_snapshot_hash(head=head, tree=tree, dirty=dirty)
        environment_hash = self._environment_hash(dependency_hash)
        return GitProvenance(
            repository_root=str(self.repository_root),
            head_commit_sha=head,
            git_tree_hash=tree,
            git_is_clean=not dirty,
            code_snapshot_hash=code_hash,
            dependency_lock_hash=dependency_hash,
            execution_environment_hash=environment_hash,
            reproducibility_status="REPRODUCIBLE" if not dirty else "NON_REPRODUCIBLE",
        )

    def _discover_root(self) -> Path:
        root = self._git("rev-parse", "--show-toplevel", cwd=Path.cwd())
        return Path(root).resolve()

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd or getattr(self, "repository_root", Path.cwd()),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            message = completed.stderr.strip() or completed.stdout.strip() or "unknown git failure"
            raise GitVerificationError(message)
        return completed.stdout.strip()

    def _dependency_lock_hash(self) -> str:
        entries: list[dict[str, str]] = []
        for path in sorted(self.repository_root.rglob("*")):
            if not path.is_file() or path.name not in self._LOCK_FILENAMES:
                continue
            entries.append(
                {
                    "path": path.relative_to(self.repository_root).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        return sha256_text(canonical_json(entries))

    def _code_snapshot_hash(self, *, head: str, tree: str, dirty: bool) -> str:
        payload: dict[str, object] = {"head": head, "tree": tree}
        if dirty:
            payload["tracked_diff_sha256"] = hashlib.sha256(
                self._git("diff", "--binary", "HEAD").encode("utf-8")
            ).hexdigest()
            untracked: list[dict[str, str]] = []
            for relative_path in filter(None, self._git("ls-files", "--others", "--exclude-standard").splitlines()):
                path = self.repository_root / relative_path
                if path.is_file():
                    untracked.append({"path": relative_path.replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            payload["untracked"] = untracked
        return sha256_text(canonical_json(payload))

    def _environment_hash(self, dependency_lock_hash: str) -> str:
        environment = {
            "dependency_lock_hash": dependency_lock_hash,
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "runtime": sys.implementation.name,
        }
        return sha256_text(canonical_json(environment))
