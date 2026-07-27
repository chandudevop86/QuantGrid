"""
rag/indexer.py

High-level RAG index manager.
"""

from __future__ import annotations

import json
from pathlib import Path

from memory.embedding_store import EmbeddingStore


class RepositoryIndexer:

    HASH_FILE = ".quantgrid_rag_index.json"

    def __init__(self):

        self.store = EmbeddingStore()

    ###############################################################

    def build(self, repo_path: str):

        print("Building repository index...")

        self.store.index_repository(repo_path)

        hashes = self.store.repository_hashes(repo_path)

        self._save_hashes(repo_path, hashes)

        print("Repository indexed successfully.")

    ###############################################################

    def update(self, repo_path: str):

        old = self._load_hashes(repo_path)

        new = self.store.update_changed_files(
            repo_path,
            old,
        )

        self._save_hashes(repo_path, new)

        print("Incremental update complete.")

    ###############################################################

    def search(
        self,
        question: str,
        limit: int = 5,
    ):

        return self.store.search(
            question,
            limit,
        )

    ###############################################################

    def rebuild(self, repo_path: str):

        self.store.vector_db.clear()

        self.build(repo_path)

    ###############################################################

    def statistics(self):

        return {
            "documents":
                self.store.vector_db.count(),
        }

    ###############################################################

    def _hash_path(
        self,
        repo_path: str,
    ) -> Path:

        return Path(repo_path) / self.HASH_FILE

    ###############################################################

    def _save_hashes(
        self,
        repo_path: str,
        hashes: dict,
    ):

        self._hash_path(repo_path).write_text(
            json.dumps(
                hashes,
                indent=2,
            )
        )

    ###############################################################

    def _load_hashes(
        self,
        repo_path: str,
    ) -> dict:

        file = self._hash_path(repo_path)

        if not file.exists():

            return {}

        return json.loads(
            file.read_text()
        )