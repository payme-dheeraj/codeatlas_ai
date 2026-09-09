"""Tree-sitter based JavaScript / JSX source code parser.

Re-uses TypeScriptParser with the JavaScript grammar, since the JS AST
structure is identical to TS for the constructs we extract — only the
grammar language binding differs.
"""

from __future__ import annotations

from typing import Any

from app.parser.languages.typescript import TypeScriptParser


class JavaScriptParser(TypeScriptParser):
    """Extracts symbols from JavaScript / JSX source using Tree-sitter.

    Inherits all parsing logic from TypeScriptParser.
    Only the grammar loading is overridden to use the JS grammar.
    """

    language_name = "javascript"
    _grammar: Any = None

    @classmethod
    def _load_grammar(cls) -> Any:
        """Load the Tree-sitter JavaScript grammar.

        Returns:
            tree_sitter.Language instance for JavaScript.
        """
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language

        return Language(tsjs.language())
