"""SQLAlchemy ORM model for parsed code symbols."""

import uuid

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ParsedSymbol(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents a single code symbol extracted from a repository file.

    A symbol is any named, addressable construct in source code:
    function, class, method, variable, import, constant, interface, etc.

    This table is the primary index for search and RAG retrieval. Every
    symbol record contains enough metadata to reconstruct a citation
    (file path + line range) and to anchor Neo4j graph nodes by ID.

    Attributes:
        id: UUID primary key.
        repo_id: FK to the parent repository.
        file_path: Relative path of the source file within the repository.
        file_type: Classified file role (controller, service, model, …).
        language: Detected programming language slug (python, typescript, …).
        symbol_kind: Type of symbol (function, class, method, import, …).
        name: Unqualified symbol name (e.g. ``"authenticate"``).
        qualified_name: Fully qualified name including class/module scope
                        (e.g. ``"AuthService.authenticate"``).
        start_line: 1-indexed line where the symbol definition begins.
        end_line: 1-indexed line where the symbol definition ends.
        docstring: Extracted docstring / JSDoc / JavaDoc comment, if any.
        signature: Function/method signature string, if applicable.
        parent_name: Name of the enclosing class or module (for methods).
        decorators: JSON list of decorator/annotation names.
        extras: Arbitrary JSON bag for language-specific metadata
                (e.g. return type, parameter types, visibility modifier).
        neo4j_node_id: The ``elementId`` assigned by Neo4j after graph write.
    """

    __tablename__ = "parsed_symbols"
    __table_args__ = (
        UniqueConstraint(
            "repo_id", "file_path", "symbol_kind", "qualified_name",
            name="uq_symbol_repo_file_kind_name",
        ),
        Index("ix_symbols_repo_language", "repo_id", "language"),
        Index("ix_symbols_repo_file", "repo_id", "file_path"),
        Index("ix_symbols_repo_kind", "repo_id", "symbol_kind"),
    )

    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False, default="generic")
    language: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    symbol_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decorators: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extras: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    neo4j_node_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ParsedSymbol {self.symbol_kind}:{self.qualified_name!r} "
            f"file={self.file_path!r} lines={self.start_line}-{self.end_line}>"
        )
