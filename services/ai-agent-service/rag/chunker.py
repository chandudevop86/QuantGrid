"""
rag/chunker.py

Repository document chunker for QuantGrid AI Agent.

Splits source files into semantic chunks suitable for embedding.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
from typing import Iterable


SUPPORTED_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".tf",
    ".sql",
    ".toml",
    ".ini",
    ".dockerfile",
}


@dataclass(slots=True)
class DocumentChunk:
    """
    Represents one chunk of text.
    """

    chunk_id: str
    source_file: str
    chunk_index: int
    text: str
    start_line: int
    end_line: int
    language: str


class RepositoryChunker:
    """
    Repository chunking engine.
    """

    def __init__(
        self,
        chunk_size: int = 120,
        overlap: int = 20,
    ) -> None:

        self.chunk_size = chunk_size
        self.overlap = overlap

    ####################################################################
    # PUBLIC
    ####################################################################

    def chunk_repository(
        self,
        repo_path: str,
    ) -> list[DocumentChunk]:

        chunks: list[DocumentChunk] = []

        root = Path(repo_path)

        for file in root.rglob("*"):

            if not file.is_file():
                continue

            if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            chunks.extend(self.chunk_file(file))

        return chunks

    def chunk_file(
        self,
        path: Path,
    ) -> list[DocumentChunk]:

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except Exception:
            return []

        lines = text.splitlines()

        if not lines:
            return []

        language = self.detect_language(path)

        return list(
            self._chunk_lines(
                path,
                lines,
                language,
            )
        )

    ####################################################################
    # INTERNAL
    ####################################################################

    def _chunk_lines(
        self,
        path: Path,
        lines: list[str],
        language: str,
    ) -> Iterable[DocumentChunk]:

        start = 0
        index = 0

        while start < len(lines):

            end = min(
                start + self.chunk_size,
                len(lines),
            )

            text = "\n".join(lines[start:end])

            chunk_id = self.build_chunk_id(
                str(path),
                index,
                text,
            )

            yield DocumentChunk(
                chunk_id=chunk_id,
                source_file=str(path),
                chunk_index=index,
                text=text,
                start_line=start + 1,
                end_line=end,
                language=language,
            )

            index += 1

            start = end - self.overlap

            if start < 0:
                start = 0

            if start >= len(lines):
                break

    ####################################################################
    # HELPERS
    ####################################################################

    @staticmethod
    def build_chunk_id(
        file_name: str,
        chunk_index: int,
        text: str,
    ) -> str:

        payload = f"{file_name}:{chunk_index}:{text}"

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def detect_language(
        path: Path,
    ) -> str:

        suffix = path.suffix.lower()

        mapping = {
            ".py": "python",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".tf": "terraform",
            ".sql": "sql",
            ".txt": "text",
            ".ini": "ini",
            ".toml": "toml",
        }

        return mapping.get(
            suffix,
            "text",
        )