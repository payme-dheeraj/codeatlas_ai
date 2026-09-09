"""Tree-sitter based TypeScript / TSX source code parser."""

from __future__ import annotations

from typing import Any

from app.parser.base import BaseLanguageParser, SymbolData


class TypeScriptParser(BaseLanguageParser):
    """Extracts symbols from TypeScript / TSX source using Tree-sitter.

    Extracted symbol kinds:
    - ``function``    — function declarations and arrow functions assigned to const
    - ``class``       — class declarations
    - ``method``      — methods inside a class body
    - ``interface``   — TypeScript interface declarations
    - ``type_alias``  — TypeScript type alias declarations
    - ``enum``        — enum declarations
    - ``import``      — import declarations
    - ``constant``    — const/let/var declarations at module level
    """

    language_name = "typescript"
    _grammar: Any = None

    @classmethod
    def _load_grammar(cls) -> Any:
        """Load the Tree-sitter TypeScript grammar.

        Returns:
            tree_sitter.Language instance for TypeScript.
        """
        import tree_sitter_typescript as tsts
        from tree_sitter import Language

        return Language(tsts.language_typescript())

    def parse(self, source: str, file_path: str) -> list[SymbolData]:
        """Parse TypeScript source and return extracted symbols.

        Args:
            source: Full TypeScript source text.
            file_path: Relative file path.

        Returns:
            List of SymbolData instances.
        """
        from tree_sitter import Parser as TSParser

        parser = TSParser(self.get_grammar())
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        symbols: list[SymbolData] = []
        self._walk(tree.root_node, source_bytes, symbols, parent_class=None)
        return symbols

    # ── Private helpers ────────────────────────────────────────────────────────

    def _walk(
        self,
        node: Any,
        source_bytes: bytes,
        symbols: list[SymbolData],
        parent_class: str | None,
    ) -> None:
        """Recursively walk the AST and collect symbols.

        Args:
            node: Current AST node.
            source_bytes: Full source bytes.
            symbols: Accumulator.
            parent_class: Enclosing class name, if any.
        """
        for child in node.children:
            t = child.type

            if t == "function_declaration":
                self._process_function(child, source_bytes, symbols, parent_class)

            elif t == "class_declaration":
                self._process_class(child, source_bytes, symbols)

            elif t == "interface_declaration":
                self._process_interface(child, source_bytes, symbols)

            elif t == "type_alias_declaration":
                self._process_type_alias(child, source_bytes, symbols)

            elif t == "enum_declaration":
                self._process_enum(child, source_bytes, symbols)

            elif t == "import_declaration":
                self._process_import(child, source_bytes, symbols)

            elif t in (
                "lexical_declaration",
                "variable_declaration",
            ) and parent_class is None:
                self._process_variable(child, source_bytes, symbols)

            elif t == "export_statement":
                # Recurse into export to catch exported declarations
                self._walk(child, source_bytes, symbols, parent_class)

            elif t == "ambient_declaration":
                self._walk(child, source_bytes, symbols, parent_class)

    def _process_function(
        self,
        node: Any,
        source_bytes: bytes,
        symbols: list[SymbolData],
        parent_class: str | None,
    ) -> None:
        name = self._get_identifier(node, source_bytes)
        if not name:
            return
        qualified = f"{parent_class}.{name}" if parent_class else name
        kind = "method" if parent_class else "function"
        doc = self._extract_jsdoc(node, source_bytes)
        sig = self._build_ts_signature(node, source_bytes, name)
        decorators = self._extract_ts_decorators(node, source_bytes)
        calls = self._extract_calls(node, source_bytes)

        symbols.append(
            SymbolData(
                name=name,
                qualified_name=qualified,
                symbol_kind=kind,
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
                signature=sig,
                parent_name=parent_class,
                decorators=decorators,
                calls=calls,
                extras={"is_async": self._has_child_type(node, "async")},
            )
        )

    def _process_class(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_identifier(node, source_bytes)
        if not name:
            return
        doc = self._extract_jsdoc(node, source_bytes)
        decorators = self._extract_ts_decorators(node, source_bytes)

        # Collect heritage (extends / implements)
        heritage: list[str] = []
        for child in node.children:
            if child.type == "class_heritage":
                heritage.append(self._node_text(child, source_bytes))

        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="class",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
                decorators=decorators,
                extras={"heritage": heritage},
            )
        )

        # Walk class body for methods
        body = self._first_child_type(node, "class_body")
        if body:
            for member in body.children:
                if member.type in ("method_definition", "public_field_definition"):
                    if member.type == "method_definition":
                        self._process_function(member, source_bytes, symbols, name)

    def _process_interface(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_identifier(node, source_bytes)
        if not name:
            return
        doc = self._extract_jsdoc(node, source_bytes)
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="interface",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
            )
        )

    def _process_type_alias(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_identifier(node, source_bytes)
        if not name:
            return
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="type_alias",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
            )
        )

    def _process_enum(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_identifier(node, source_bytes)
        if not name:
            return
        members: list[str] = []
        body = self._first_child_type(node, "enum_body")
        if body:
            for child in body.children:
                if child.type == "property_identifier":
                    members.append(self._node_text(child, source_bytes))
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="enum",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                extras={"members": members},
            )
        )

    def _process_import(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        text = self._node_text(node, source_bytes).strip()
        name = text.split("\n")[0][:200]
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="import",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                imports=[name],
            )
        )

    def _process_variable(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        """Extract const/let/var declarations (including arrow function consts)."""
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node is None:
                    continue
                name = self._node_text(name_node, source_bytes)
                if not name or not name[0].isalpha():
                    continue

                # Arrow function assigned to a const
                if value_node and value_node.type in (
                    "arrow_function",
                    "function",
                    "function_expression",
                ):
                    sig = f"const {name} = {self._node_text(value_node, source_bytes)[:80]}"
                    calls = self._extract_calls(value_node, source_bytes)
                    symbols.append(
                        SymbolData(
                            name=name,
                            qualified_name=name,
                            symbol_kind="function",
                            start_line=self._line_of(node),
                            end_line=self._end_line_of(node),
                            signature=sig,
                            calls=calls,
                            extras={"is_arrow": True},
                        )
                    )
                else:
                    # Plain constant
                    symbols.append(
                        SymbolData(
                            name=name,
                            qualified_name=name,
                            symbol_kind="constant",
                            start_line=self._line_of(node),
                            end_line=self._end_line_of(node),
                        )
                    )

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _get_identifier(self, node: Any, source_bytes: bytes) -> str:
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return self._node_text(child, source_bytes)
        return ""

    def _first_child_type(self, node: Any, type_: str) -> Any | None:
        for child in node.children:
            if child.type == type_:
                return child
        return None

    def _has_child_type(self, node: Any, type_: str) -> bool:
        return any(c.type == type_ for c in node.children)

    def _extract_jsdoc(self, node: Any, source_bytes: bytes) -> str | None:
        """Look for a JSDoc comment immediately preceding the node."""
        prev = node.prev_sibling
        if prev and prev.type in ("comment", "template_literal"):
            raw = self._node_text(prev, source_bytes)
            if raw.startswith("/**") or raw.startswith("//"):
                return self._clean_docstring(raw)
        return None

    def _extract_ts_decorators(self, node: Any, source_bytes: bytes) -> list[str]:
        result: list[str] = []
        for child in node.children:
            if child.type == "decorator":
                for sub in child.children:
                    if sub.type in ("identifier", "call_expression"):
                        text = self._node_text(sub, source_bytes).split("(")[0]
                        result.append(text)
                        break
        return result

    def _build_ts_signature(
        self, node: Any, source_bytes: bytes, name: str
    ) -> str | None:
        params = self._first_child_type(node, "formal_parameters")
        ret = self._first_child_type(node, "type_annotation")
        if params is None:
            return None
        params_str = self._node_text(params, source_bytes)
        ret_str = (
            f": {self._node_text(ret, source_bytes)}" if ret else ""
        )
        return f"function {name}{params_str}{ret_str}"

    def _extract_calls(self, node: Any, source_bytes: bytes) -> list[str]:
        calls: set[str] = set()

        def _rec(n: Any) -> None:
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func:
                    calls.add(self._node_text(func, source_bytes).split("(")[0].strip())
            for c in n.children:
                _rec(c)

        _rec(node)
        return sorted(calls)
