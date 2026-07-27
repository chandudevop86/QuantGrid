"""
rag/retriever.py

Retrieves the most relevant code chunks from the vector database.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag.embedding import EmbeddingService
from memory.vector_store import VectorStore


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    file: str
    text: str
    language: str
    start_line: int
    end_line: int


class Retriever:

    def __init__(
        self,
        top_k: int = 8,
    ):

        self.embedding = EmbeddingService()
        self.vector_store = VectorStore()
        self.top_k = top_k

    ##################################################################

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:

        embedding = self.embedding.embed_query(question)

        rows = self.vector_store.search(
            embedding,
            limit=top_k or self.top_k,
        )

        return [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                file=row["file"],
                text=row["text"],
                language=row["language"],
                start_line=row["start_line"],
                end_line=row["end_line"],
            )
            for row in rows
        ]

    ##################################################################

    def build_context(
        self,
        question: str,
        top_k: int | None = None,
    ) -> str:

        chunks = self.retrieve(question, top_k)

        context = []

        for chunk in chunks:

            context.append(
                f"""
================================================
FILE : {chunk.file}

LINES : {chunk.start_line}-{chunk.end_line}

{chunk.text}
"""
            )

        return "\n".join(context)

    ##################################################################

    def search_files(
        self,
        question: str,
    ) -> list[str]:

        chunks = self.retrieve(question)

        files = []

        for chunk in chunks:

            if chunk.file not in files:
                files.append(chunk.file)

        return files