"""Abstract base class for all language-specific parsers.

Every language parser must implement ``parse()`` which accepts raw source
code and returns a list of ``SymbolData`` dataclasses — plain data objects
with no ORM or Pydantic dependencies.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SymbolData:
    """Language-agnostic representation of a single parsed code symbol.

    This dataclass is the internal currency between language parsers,
    the parser service, and the Neo4j writer. It is converted to a
    ``ParsedSymbol`` ORM dict before database persistence.

    Attributes:
        name: Unqualified symbol name.
        qualified_name: Fully scoped name (e.g. ``"AuthService.login"``).
        symbol_kind: Type string: function | class | method | import |
                     constant | interface | enum | type_alias | variable.
        start_line: 1-indexed line where the definition begins.
        end_line: 1-indexed line where the definition ends.
        docstring: Extracted documentation comment, stripped of delimiters.
        signature: Signature string for functions/methods.
        parent_name: Enclosing class or module name, if applicable.
        decorators: List of decorator/annotation identifier strings.
        extras: Language-specific metadata (return type, parameter info, etc.).
        calls: List of names that this symbol calls (for call graph).
        imports: List of module/file paths this file imports (for import graph).
    """

    name: str
    qualified_name: str
    symbol_kind: str
    start_line: int
    end_line: int
    docstring: str | None = None
    signature: str | None = None
    parent_name: str | None = None
    decorators: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


class BaseLanguageParser(ABC):
    """Abstract base for all language-specific Tree-sitter parsers.

    Subclasses must set the ``language_name`` class variable and implement
    ``parse()``. The ``_load_grammar()`` method is called lazily and cached
    at the class level to avoid re-loading grammars on every file.

    Attributes:
        language_name: Canonical language slug (e.g. ``"python"``).
        _grammar: Cached Tree-sitter Language object (class-level).
    """

    language_name: str = ""
    _grammar: Any = None  # tree_sitter.Language, cached at class level

    @classmethod
    def _load_grammar(cls) -> Any:
        """Load and cache the Tree-sitter grammar for this language.

        Called automatically by ``parse()`` on first use.

        Returns:
            A tree_sitter.Language instance.

        Raises:
            ImportError: If the tree-sitter grammar package is missing.
            RuntimeError: If grammar loading fails for another reason.
        """
        raise NotImplementedError(
            f"{cls.__name__} must implement _load_grammar()."
        )

    @classmethod
    def get_grammar(cls) -> Any:
        """Return the cached grammar, loading it on first access.

        Returns:
            A tree_sitter.Language instance.
        """
        if cls._grammar is None:
            cls._grammar = cls._load_grammar()
        return cls._grammar

    @abstractmethod
    def parse(self, source: str, file_path: str) -> list[SymbolData]:
        """Parse source code and return all extracted symbols.

        Args:
            source: Full UTF-8 source text of the file.
            file_path: Relative path of the file (used for qualified name scoping).

        Returns:
            List of SymbolData instances, one per extracted symbol.
        """
        ...

    # ── Shared helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _node_text(node: Any, source_bytes: bytes) -> str:
        """Extract raw text for a Tree-sitter node from the source bytes.

        Args:
            node: A tree_sitter.Node instance.
            source_bytes: The full UTF-8 encoded source as bytes.

        Returns:
            Decoded text string for the node's byte range.
        """
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _clean_docstring(raw: str) -> str | None:
        """Strip comment delimiters and normalise whitespace from a docstring.

        Handles Python triple-quotes, ``//`` line comments, ``/* */`` blocks,
        ``#`` shell comments, and ``/** */`` JavaDoc.

        Args:
            raw: Raw comment text as extracted from the AST.

        Returns:
            Cleaned docstring string, or None if the result is empty.
        """
        if not raw:
            return None
        # Remove triple-quote Python docstrings
        cleaned = re.sub(r'^[\'\"]{3}|[\'\"]{3}$', '', raw.strip())
        # Remove JavaDoc / block comment delimiters
        cleaned = re.sub(r'^/\*\*?|\*/$', '', cleaned.strip())
        # Remove leading * on each line (block comment style)
        cleaned = re.sub(r'^\s*\*\s?', '', cleaned, flags=re.MULTILINE)
        # Remove // line comments
        cleaned = re.sub(r'^\s*//\s?', '', cleaned, flags=re.MULTILINE)
        # Remove # line comments
        cleaned = re.sub(r'^\s*#\s?', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        return cleaned if cleaned else None

    @staticmethod
    def _line_of(node: Any) -> int:
        """Return 1-indexed start line for a Tree-sitter node.

        Args:
            node: A tree_sitter.Node instance.

        Returns:
            1-indexed line number.
        """
        return node.start_point[0] + 1

    @staticmethod
    def _end_line_of(node: Any) -> int:
        """Return 1-indexed end line for a Tree-sitter node.

        Args:
            node: A tree_sitter.Node instance.

        Returns:
            1-indexed line number.
        """
        return node.end_point[0] + 1
