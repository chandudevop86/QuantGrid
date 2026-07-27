"""
memory/embedding_store.py

Indexes repositories into the vector database.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag.chunker import RepositoryChunker
from rag.embedding import EmbeddingService
from memory.vector_store import VectorStore


class EmbeddingStore:
    """
    Repository indexing service.
    """

    def __init__(self) -> None:

        self.chunker = RepositoryChunker()

        self.embedding = EmbeddingService()

        self.vector_db = VectorStore()

    ####################################################################

    def index_repository(
        self,
        repo_path: str,
    ) -> None:

        chunks = self.chunker.chunk_repository(repo_path)

        print(f"Chunks: {len(chunks)}")

        for chunk in chunks:

            vector = self.embedding.embed_text(
                chunk.text
            )

            self.vector_db.add_document(

                chunk_id=chunk.chunk_id,

                source_file=chunk.source_file,

                chunk_index=chunk.chunk_index,

                start_line=chunk.start_line,

                end_line=chunk.end_line,

                language=chunk.language,

                text=chunk.text,

                embedding=vector,
            )

    ####################################################################

    def index_file(
        self,
        file_path: str,
    ) -> None:

        chunks = self.chunker.chunk_file(
            Path(file_path)
        )

        self.vector_db.delete_file(file_path)

        for chunk in chunks:

            vector = self.embedding.embed_text(
                chunk.text
            )

            self.vector_db.add_document(

                chunk_id=chunk.chunk_id,

                source_file=chunk.source_file,

                chunk_index=chunk.chunk_index,

                start_line=chunk.start_line,

                end_line=chunk.end_line,

                language=chunk.language,

                text=chunk.text,

                embedding=vector,
            )

    ####################################################################

    def file_hash(
        self,
        file_path: str,
    ) -> str:

        return hashlib.sha256(

            Path(file_path)
            .read_bytes()

        ).hexdigest()

    ####################################################################

    def repository_hashes(
        self,
        repo_path: str,
    ) -> dict[str, str]:

        hashes = {}

        for file in Path(repo_path).rglob("*"):

            if file.is_file():

                try:

                    hashes[str(file)] = self.file_hash(
                        str(file)
                    )

                except Exception:
                    pass

        return hashes

    ####################################################################

    def update_changed_files(
        self,
        repo_path: str,
        previous_hashes: dict[str, str],
    ) -> dict[str, str]:

        current = self.repository_hashes(repo_path)

        for file, hash_value in current.items():

            if previous_hashes.get(file) != hash_value:

                print("Updating:", file)

                self.index_file(file)

        return current

    ####################################################################

    def search(
        self,
        question: str,
        limit: int = 5,
    ):

        vector = self.embedding.embed_query(question)

        return self.vector_db.search(
            vector,
            limit,
        )