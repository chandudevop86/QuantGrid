"""
rag/embedding.py

Embedding service for QuantGrid AI Agent.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    OpenAI embedding service.
    """

    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_retries: int = 3,
    ) -> None:

        self.model = model or self.DEFAULT_MODEL
        self.max_retries = max_retries

        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY")
        )

    ####################################################################
    # PUBLIC
    ####################################################################

    def embed_text(
        self,
        text: str,
    ) -> list[float]:

        if not text.strip():
            return []

        return self._embed(text)

    def embed_query(
        self,
        query: str,
    ) -> list[float]:

        return self.embed_text(query)

    def embed_batch(
        self,
        texts: Iterable[str],
    ) -> list[list[float]]:

        items = [
            t.strip()
            for t in texts
            if t.strip()
        ]

        if not items:
            return []

        for attempt in range(self.max_retries):

            try:

                response = self.client.embeddings.create(
                    model=self.model,
                    input=items,
                )

                return [
                    item.embedding
                    for item in response.data
                ]

            except Exception as exc:

                logger.warning(
                    "Batch embedding failed (%s/%s): %s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                )

                time.sleep(2)

        raise RuntimeError(
            "Unable to generate embeddings."
        )

    ####################################################################
    # PRIVATE
    ####################################################################

    def _embed(
        self,
        text: str,
    ) -> list[float]:

        for attempt in range(self.max_retries):

            try:

                response = self.client.embeddings.create(
                    model=self.model,
                    input=text,
                )

                return response.data[0].embedding

            except Exception as exc:

                logger.warning(
                    "Embedding failed (%s/%s): %s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                )

                time.sleep(2)

        raise RuntimeError(
            "Embedding generation failed."
        )

    ####################################################################
    # UTILITIES
    ####################################################################

    @staticmethod
    def cosine_similarity(
        vector1: list[float],
        vector2: list[float],
    ) -> float:

        if len(vector1) != len(vector2):
            raise ValueError(
                "Embedding dimensions differ."
            )

        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0

        for a, b in zip(vector1, vector2):

            dot += a * b
            norm_a += a * a
            norm_b += b * b

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (
            (norm_a ** 0.5)
            * (norm_b ** 0.5)
        )

    @staticmethod
    def embedding_dimension(
        embedding: list[float],
    ) -> int:

        return len(embedding)