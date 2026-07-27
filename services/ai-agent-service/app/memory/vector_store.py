"""
memory/vector_store.py

PostgreSQL + pgvector vector database.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

load_dotenv()


##############################################################################
# DATABASE
##############################################################################

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/quantgrid",
)

ENGINE = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=ENGINE,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


##############################################################################
# TABLE
##############################################################################


class VectorDocument(Base):

    __tablename__ = "rag_vectors"

    id = Column(Integer, primary_key=True)

    chunk_id = Column(
        String(100),
        unique=True,
        nullable=False,
    )

    source_file = Column(String(500))

    chunk_index = Column(Integer)

    start_line = Column(Integer)

    end_line = Column(Integer)

    language = Column(String(40))

    text = Column(Text)

    score = Column(
        Float,
        default=0,
    )

    embedding = Column(
        Vector(1536),
    )


##############################################################################
# STORE
##############################################################################


class VectorStore:

    def __init__(self):

        Base.metadata.create_all(
            ENGINE
        )

    ###############################################################

    def add_document(
        self,
        *,
        chunk_id: str,
        source_file: str,
        chunk_index: int,
        start_line: int,
        end_line: int,
        language: str,
        text: str,
        embedding: list[float],
    ) -> None:

        with SessionLocal() as db:

            exists = (
                db.query(VectorDocument)
                .filter_by(chunk_id=chunk_id)
                .first()
            )

            if exists:
                return

            doc = VectorDocument(

                chunk_id=chunk_id,

                source_file=source_file,

                chunk_index=chunk_index,

                start_line=start_line,

                end_line=end_line,

                language=language,

                text=text,

                embedding=embedding,

            )

            db.add(doc)

            db.commit()

    ###############################################################

    def search(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:

        with SessionLocal() as db:

            rows = (
                db.query(VectorDocument)
                .order_by(
                    VectorDocument.embedding.cosine_distance(
                        embedding
                    )
                )
                .limit(limit)
                .all()
            )

            results = []

            for row in rows:

                results.append(
                    {
                        "chunk_id": row.chunk_id,
                        "file": row.source_file,
                        "text": row.text,
                        "language": row.language,
                        "start_line": row.start_line,
                        "end_line": row.end_line,
                    }
                )

            return results

    ###############################################################

    def delete_file(
        self,
        file_path: str,
    ):

        with SessionLocal() as db:

            db.query(
                VectorDocument
            ).filter(
                VectorDocument.source_file == file_path
            ).delete()

            db.commit()

    ###############################################################

    def count(self) -> int:

        with SessionLocal() as db:

            return db.query(
                VectorDocument
            ).count()

    ###############################################################

    def clear(self):

        with SessionLocal() as db:

            db.query(
                VectorDocument
            ).delete()

            db.commit()