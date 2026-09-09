"""Tree-sitter based Go source code parser."""

from __future__ import annotations

from typing import Any

from app.parser.base import BaseLanguageParser, SymbolData


class GoParser(BaseLanguageParser):
    """Extracts symbols from Go source using Tree-sitter.

    Extracted symbol kinds:
    - ``function``   — top-level function declarations
    - ``method``     — methods with a receiver type
    - ``class``      — struct type declarations (Go's nearest class equivalent)
    - ``interface``  — interface type declarations
    - ``import``     — import declarations
    - ``constant``   — const declarations
    - ``variable``   — var declarations at package level
    """

    language_name = "go"
    _grammar: Any = None

    @classmethod
    def _load_grammar(cls) -> Any:
        """Load the Tree-sitter Go grammar.

        Returns:
            tree_sitter.Language instance for Go.
        """
        import tree_sitter_go as tsgo
        from tree_sitter import Language

        return Language(tsgo.language())

    def parse(self, source: str, file_path: str) -> list[SymbolData]:
        """Parse Go source and return extracted symbols.

        Args:
            source: Full Go source text.
            file_path: Relative file path.

        Returns:
            List of SymbolData instances.
        """
        from tree_sitter import Parser as TSParser

        parser = TSParser(self.get_grammar())
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        symbols: list[SymbolData] = []
        self._walk(tree.root_node, source_bytes, symbols)
        return symbols

    # ── Private helpers ────────────────────────────────────────────────────────

    def _walk(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        for child in node.children:
            t = child.type
            if t == "function_declaration":
                self._process_function(child, source_bytes, symbols)
            elif t == "method_declaration":
                self._process_method(child, source_bytes, symbols)
            elif t == "type_declaration":
                self._process_type_decl(child, source_bytes, symbols)
            elif t == "import_declaration":
                self._process_import(child, source_bytes, symbols)
            elif t == "const_declaration":
                self._process_const(child, source_bytes, symbols)
            elif t == "var_declaration":
                self._process_var(child, source_bytes, symbols)

    def _process_function(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_identifier(node, source_bytes)
        if not name:
            return
        doc = self._extract_go_comment(node, source_bytes)
        sig = self._build_go_signature(node, source_bytes)
        calls = self._extract_calls(node, source_bytes)

        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="function",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
                signature=sig,
                calls=calls,
            )
        )

    def _process_method(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_identifier(node, source_bytes)
        if not name:
            return

        # Extract receiver type name
        receiver_name: str | None = None
        params_node = node.child_by_field_name("receiver")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter_declaration":
                    for sub in child.children:
                        if sub.type in ("type_identifier", "pointer_type"):
                            raw = self._node_text(sub, source_bytes)
                            receiver_name = raw.lstrip("*")
                            break

        qualified = f"{receiver_name}.{name}" if receiver_name else name
        doc = self._extract_go_comment(node, source_bytes)
        sig = self._build_go_signature(node, source_bytes)
        calls = self._extract_calls(node, source_bytes)

        symbols.append(
            SymbolData(
                name=name,
                qualified_name=qualified,
                symbol_kind="method",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
                signature=sig,
                parent_name=receiver_name,
                calls=calls,
            )
        )

    def _process_type_decl(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node is None or type_node is None:
                    continue
                name = self._node_text(name_node, source_bytes)
                kind_map = {
                    "struct_type": "class",
                    "interface_type": "interface",
                }
                kind = kind_map.get(type_node.type, "type_alias")
                doc = self._extract_go_comment(node, source_bytes)
                symbols.append(
                    SymbolData(
                        name=name,
                        qualified_name=name,
                        symbol_kind=kind,
                        start_line=self._line_of(node),
                        end_line=self._end_line_of(node),
                        docstring=doc,
                    )
                )

    def _process_import(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        text = self._node_text(node, source_bytes).strip()
        name = text[:200]
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

    def _process_const(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        for child in node.children:
            if child.type == "const_spec":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = self._node_text(name_node, source_bytes)
                    symbols.append(
                        SymbolData(
                            name=name,
                            qualified_name=name,
                            symbol_kind="constant",
                            start_line=self._line_of(node),
                            end_line=self._end_line_of(node),
                        )
                    )

    def _process_var(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        for child in node.children:
            if child.type == "var_spec":
                for sub in child.children:
                    if sub.type == "identifier":
                        name = self._node_text(sub, source_bytes)
                        symbols.append(
                            SymbolData(
                                name=name,
                                qualified_name=name,
                                symbol_kind="variable",
                                start_line=self._line_of(node),
                                end_line=self._end_line_of(node),
                            )
                        )
                        break

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _get_identifier(self, node: Any, source_bytes: bytes) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._node_text(name_node, source_bytes)
        for child in node.children:
            if child.type == "identifier":
                return self._node_text(child, source_bytes)
        return ""

    def _extract_go_comment(self, node: Any, source_bytes: bytes) -> str | None:
        prev = node.prev_sibling
        if prev and prev.type == "comment":
            return self._clean_docstring(self._node_text(prev, source_bytes))
        return None

    def _build_go_signature(self, node: Any, source_bytes: bytes) -> str | None:
        params = node.child_by_field_name("parameters")
        result = node.child_by_field_name("result")
        name_node = node.child_by_field_name("name")
        if params is None or name_node is None:
            return None
        name = self._node_text(name_node, source_bytes)
        params_str = self._node_text(params, source_bytes)
        ret_str = (
            f" {self._node_text(result, source_bytes)}" if result else ""
        )
        return f"func {name}{params_str}{ret_str}"

    def _extract_calls(self, node: Any, source_bytes: bytes) -> list[str]:
        calls: set[str] = set()

        def _rec(n: Any) -> None:
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func:
                    calls.add(self._node_text(func, source_bytes).strip())
            for c in n.children:
                _rec(c)

        _rec(node)
        return sorted(calls)
