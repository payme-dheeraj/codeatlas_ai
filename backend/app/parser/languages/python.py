"""Tree-sitter based Python source code parser."""

from __future__ import annotations

from typing import Any

from app.parser.base import BaseLanguageParser, SymbolData

# Tree-sitter node type constants for Python grammar
_FUNC_DEF = "function_definition"
_ASYNC_FUNC_DEF = "async_function_definition"
_CLASS_DEF = "class_definition"
_IMPORT = "import_statement"
_IMPORT_FROM = "import_from_statement"
_EXPR_STMT = "expression_statement"
_ASSIGNMENT = "assignment"
_DECORATED_DEF = "decorated_definition"
_DECORATOR = "decorator"


class PythonParser(BaseLanguageParser):
    """Extracts symbols from Python source using Tree-sitter.

    Extracted symbol kinds:
    - ``function`` — module-level function definitions (sync and async)
    - ``class`` — class definitions
    - ``method`` — functions nested inside a class body
    - ``import`` — import and from-import statements
    - ``constant`` — module-level UPPER_SNAKE_CASE assignments
    """

    language_name = "python"
    _grammar: Any = None

    @classmethod
    def _load_grammar(cls) -> Any:
        """Load the Tree-sitter Python grammar.

        Returns:
            tree_sitter.Language instance for Python.
        """
        import tree_sitter_python as tspython
        from tree_sitter import Language

        return Language(tspython.language())

    def parse(self, source: str, file_path: str) -> list[SymbolData]:
        """Parse Python source and return extracted symbols.

        Args:
            source: Full Python source text.
            file_path: Relative file path (used for module name inference).

        Returns:
            List of SymbolData instances.
        """
        from tree_sitter import Parser as TSParser

        parser = TSParser(self.get_grammar())
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        symbols: list[SymbolData] = []
        self._walk_module(tree.root_node, source_bytes, file_path, symbols)
        return symbols

    # ── Private helpers ────────────────────────────────────────────────────────

    def _walk_module(
        self,
        node: Any,
        source_bytes: bytes,
        file_path: str,
        symbols: list[SymbolData],
        parent_class: str | None = None,
    ) -> None:
        """Recursively walk the AST and collect symbols.

        Args:
            node: Current Tree-sitter node.
            source_bytes: Full source as bytes.
            file_path: Relative file path.
            symbols: Accumulator list for collected SymbolData.
            parent_class: Name of the enclosing class, if any.
        """
        for child in node.children:
            kind = child.type

            # ── Decorated definitions ────────────────────────────────────────
            if kind == _DECORATED_DEF:
                decorators = self._extract_decorators(child, source_bytes)
                inner = self._first_child_of_type(
                    child, (_FUNC_DEF, _ASYNC_FUNC_DEF, _CLASS_DEF)
                )
                if inner is not None:
                    self._process_def(
                        inner, source_bytes, file_path, symbols, parent_class, decorators
                    )
                continue

            # ── Plain function / async function ──────────────────────────────
            if kind in (_FUNC_DEF, _ASYNC_FUNC_DEF):
                self._process_def(child, source_bytes, file_path, symbols, parent_class)
                continue

            # ── Class definition ─────────────────────────────────────────────
            if kind == _CLASS_DEF:
                self._process_def(child, source_bytes, file_path, symbols, parent_class)
                # Recurse into class body for methods
                body = self._first_child_of_type(child, ("block",))
                if body:
                    class_name = self._get_name(child, source_bytes)
                    self._walk_module(body, source_bytes, file_path, symbols, class_name)
                continue

            # ── Imports ──────────────────────────────────────────────────────
            if kind in (_IMPORT, _IMPORT_FROM) and parent_class is None:
                sym = self._process_import(child, source_bytes, file_path)
                if sym:
                    symbols.append(sym)
                continue

            # ── Module-level constants ────────────────────────────────────────
            if kind in (_EXPR_STMT, _ASSIGNMENT) and parent_class is None:
                sym = self._process_assignment(child, source_bytes, file_path)
                if sym:
                    symbols.append(sym)

    def _process_def(
        self,
        node: Any,
        source_bytes: bytes,
        file_path: str,
        symbols: list[SymbolData],
        parent_class: str | None = None,
        decorators: list[str] | None = None,
    ) -> None:
        """Extract a function, async function, or class definition as a symbol.

        Args:
            node: The function_definition or class_definition node.
            source_bytes: Full source bytes.
            file_path: Relative file path.
            symbols: Accumulator.
            parent_class: Enclosing class name, if any.
            decorators: Pre-extracted decorator names, if any.
        """
        name = self._get_name(node, source_bytes)
        if not name:
            return

        qualified = f"{parent_class}.{name}" if parent_class else name
        is_class = node.type == _CLASS_DEF
        kind = "class" if is_class else ("method" if parent_class else "function")

        # Docstring: first statement in body if it's a string literal
        docstring = self._extract_docstring(node, source_bytes)

        # Signature for functions/methods
        signature = None
        if not is_class:
            params_node = self._first_child_of_type(node, ("parameters",))
            ret_node = self._first_child_of_type(node, ("type",))
            params = (
                self._node_text(params_node, source_bytes) if params_node else "()"
            )
            ret = (
                f" -> {self._node_text(ret_node, source_bytes)}" if ret_node else ""
            )
            signature = f"def {name}{params}{ret}"

        # Calls inside function body
        calls: list[str] = []
        if not is_class:
            body = self._first_child_of_type(node, ("block",))
            if body:
                calls = self._extract_calls(body, source_bytes)

        symbols.append(
            SymbolData(
                name=name,
                qualified_name=qualified,
                symbol_kind=kind,
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=docstring,
                signature=signature,
                parent_name=parent_class,
                decorators=decorators or [],
                calls=calls,
                extras={
                    "is_async": node.type == _ASYNC_FUNC_DEF,
                },
            )
        )

    def _process_import(
        self, node: Any, source_bytes: bytes, file_path: str
    ) -> SymbolData | None:
        """Extract an import statement as a symbol.

        Args:
            node: The import_statement or import_from_statement node.
            source_bytes: Full source bytes.
            file_path: Relative file path.

        Returns:
            SymbolData for the import, or None.
        """
        text = self._node_text(node, source_bytes).strip()
        # Use the raw import text as both name and qualified_name
        name = text.split("\n")[0][:200]
        return SymbolData(
            name=name,
            qualified_name=name,
            symbol_kind="import",
            start_line=self._line_of(node),
            end_line=self._end_line_of(node),
            imports=[name],
        )

    def _process_assignment(
        self, node: Any, source_bytes: bytes, file_path: str
    ) -> SymbolData | None:
        """Extract a module-level UPPER_CASE assignment as a constant symbol.

        Args:
            node: An assignment or expression_statement node.
            file_path: Relative file path.

        Returns:
            SymbolData if the left-hand side is UPPER_CASE, else None.
        """
        # Only interested in simple name = value at module level
        name_node = None
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break
            if child.type == "assignment":
                for sub in child.children:
                    if sub.type == "identifier":
                        name_node = sub
                        break
                break

        if name_node is None:
            return None
        name = self._node_text(name_node, source_bytes)
        # Only collect UPPER_SNAKE_CASE constants
        if not name.isupper():
            return None

        return SymbolData(
            name=name,
            qualified_name=name,
            symbol_kind="constant",
            start_line=self._line_of(node),
            end_line=self._end_line_of(node),
        )

    def _get_name(self, node: Any, source_bytes: bytes) -> str:
        """Extract the ``name`` child identifier text from a definition node.

        Args:
            node: A function_definition or class_definition node.
            source_bytes: Full source bytes.

        Returns:
            Name string, or empty string if not found.
        """
        for child in node.children:
            if child.type == "identifier":
                return self._node_text(child, source_bytes)
        return ""

    def _extract_docstring(self, node: Any, source_bytes: bytes) -> str | None:
        """Extract the first string literal from a function/class body as docstring.

        Args:
            node: Function or class definition node.
            source_bytes: Full source bytes.

        Returns:
            Cleaned docstring, or None.
        """
        body = self._first_child_of_type(node, ("block",))
        if body is None:
            return None
        for child in body.children:
            if child.type == _EXPR_STMT:
                for sub in child.children:
                    if sub.type in ("string", "concatenated_string"):
                        raw = self._node_text(sub, source_bytes)
                        return self._clean_docstring(raw)
            break  # Only check the very first statement
        return None

    def _extract_decorators(self, decorated_node: Any, source_bytes: bytes) -> list[str]:
        """Extract decorator names from a decorated_definition node.

        Args:
            decorated_node: A decorated_definition node.
            source_bytes: Full source bytes.

        Returns:
            List of decorator identifier strings.
        """
        result: list[str] = []
        for child in decorated_node.children:
            if child.type == _DECORATOR:
                # Take the identifier immediately after @
                for sub in child.children:
                    if sub.type in ("identifier", "attribute", "call"):
                        result.append(self._node_text(sub, source_bytes).split("(")[0])
                        break
        return result

    def _extract_calls(self, body_node: Any, source_bytes: bytes) -> list[str]:
        """Collect all call expression names within a function body.

        Args:
            body_node: The block/body node of a function.
            source_bytes: Full source bytes.

        Returns:
            Deduplicated list of called function/method names.
        """
        calls: set[str] = set()

        def _recurse(node: Any) -> None:
            if node.type == "call":
                func_node = node.child_by_field_name("function")
                if func_node:
                    text = self._node_text(func_node, source_bytes)
                    # Strip argument details; keep qualified name
                    calls.add(text.split("(")[0].strip())
            for child in node.children:
                _recurse(child)

        _recurse(body_node)
        return sorted(calls)

    @staticmethod
    def _first_child_of_type(node: Any, types: tuple[str, ...]) -> Any | None:
        """Return the first direct child whose type is in ``types``.

        Args:
            node: Parent Tree-sitter node.
            types: Tuple of acceptable node type strings.

        Returns:
            First matching child node, or None.
        """
        for child in node.children:
            if child.type in types:
                return child
        return None
