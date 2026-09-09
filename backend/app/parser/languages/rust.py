"""Tree-sitter based Rust source code parser."""

from __future__ import annotations

from typing import Any

from app.parser.base import BaseLanguageParser, SymbolData


class RustParser(BaseLanguageParser):
    """Extracts symbols from Rust source using Tree-sitter.

    Extracted symbol kinds:
    - ``function``   — top-level or module functions
    - ``method``     — methods inside impl blocks
    - ``class``      — struct definitions (Rust's primary data entity)
    - ``enum``       — enum definitions
    - ``interface``  — trait definitions
    - ``import``     — use declarations
    - ``constant``   — const items
    - ``type_alias`` — type alias declarations
    """

    language_name = "rust"
    _grammar: Any = None

    @classmethod
    def _load_grammar(cls) -> Any:
        """Load the Tree-sitter Rust grammar.

        Returns:
            tree_sitter.Language instance for Rust.
        """
        import tree_sitter_rust as tsrust
        from tree_sitter import Language

        return Language(tsrust.language())

    def parse(self, source: str, file_path: str) -> list[SymbolData]:
        """Parse Rust source and return extracted symbols.

        Args:
            source: Full Rust source text.
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
        self,
        node: Any,
        source_bytes: bytes,
        symbols: list[SymbolData],
        parent_name: str | None = None,
    ) -> None:
        """Recursively walk the AST and process definitions."""
        for child in node.children:
            t = child.type
            if t == "function_item":
                self._process_function(child, source_bytes, symbols, parent_name=parent_name)
            elif t == "struct_item":
                self._process_struct(child, source_bytes, symbols)
            elif t == "enum_item":
                self._process_enum(child, source_bytes, symbols)
            elif t == "trait_item":
                self._process_trait(child, source_bytes, symbols)
            elif t == "impl_item":
                self._process_impl(child, source_bytes, symbols)
            elif t == "mod_item":
                self._process_mod(child, source_bytes, symbols)
            elif t == "use_declaration":
                self._process_use(child, source_bytes, symbols)
            elif t == "const_item":
                self._process_const(child, source_bytes, symbols)
            elif t == "type_item":
                self._process_type_item(child, source_bytes, symbols)

    def _process_function(
        self,
        node: Any,
        source_bytes: bytes,
        symbols: list[SymbolData],
        parent_name: str | None = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node, source_bytes)
        if not name:
            return

        is_method = parent_name is not None
        qualified = f"{parent_name}.{name}" if is_method else name
        kind = "method" if is_method else "function"

        doc = self._extract_rust_doc(node, source_bytes)
        sig = self._build_function_signature(node, source_bytes)
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
                parent_name=parent_name,
                calls=calls,
            )
        )

    def _process_struct(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node, source_bytes)
        if not name:
            return

        doc = self._extract_rust_doc(node, source_bytes)
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="class",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
            )
        )

    def _process_enum(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node, source_bytes)
        if not name:
            return

        doc = self._extract_rust_doc(node, source_bytes)
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="enum",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
            )
        )

    def _process_trait(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node, source_bytes)
        if not name:
            return

        doc = self._extract_rust_doc(node, source_bytes)
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

        body = node.child_by_field_name("body")
        if body:
            self._walk(body, source_bytes, symbols, parent_name=name)

    def _process_impl(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        type_node = node.child_by_field_name("type")
        trait_node = node.child_by_field_name("trait")

        type_name = self._node_text(type_node, source_bytes) if type_node else None
        trait_name = self._node_text(trait_node, source_bytes) if trait_node else None

        scope_name = type_name or "impl"
        if trait_name and type_name:
            scope_name = f"{trait_name} for {type_name}"

        body = node.child_by_field_name("body")
        if body:
            self._walk(body, source_bytes, symbols, parent_name=type_name or scope_name)

    def _process_mod(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node, source_bytes)
        if not name:
            return

        doc = self._extract_rust_doc(node, source_bytes)
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="module",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
            )
        )
        body = node.child_by_field_name("body")
        if body:
            self._walk(body, source_bytes, symbols, parent_name=name)

    def _process_use(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        raw = self._node_text(node, source_bytes)
        cleaned = raw.replace("use ", "").rstrip(";").strip()
        symbols.append(
            SymbolData(
                name=cleaned,
                qualified_name=cleaned,
                symbol_kind="import",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                imports=[cleaned],
            )
        )

    def _process_const(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node, source_bytes)
        if not name:
            return
        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="constant",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
            )
        )

    def _process_type_item(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node, source_bytes)
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

    # ── Text extraction helpers ───────────────────────────────────────────────

    def _build_function_signature(self, node: Any, source_bytes: bytes) -> str:
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        return_node = node.child_by_field_name("return_type")

        name = self._node_text(name_node, source_bytes) if name_node else "fn"
        params = self._node_text(params_node, source_bytes) if params_node else "()"
        ret = f" -> {self._node_text(return_node, source_bytes)}" if return_node else ""
        return f"fn {name}{params}{ret}"

    def _extract_rust_doc(self, node: Any, source_bytes: bytes) -> str | None:
        """Extract /// doc comments directly preceding the node."""
        comments: list[str] = []
        prev = node.prev_sibling
        while prev and prev.type in ("line_comment", "block_comment"):
            text = self._node_text(prev, source_bytes).strip()
            if text.startswith("///"):
                comments.insert(0, text.lstrip("/").strip())
            elif text.startswith("/**") and text.endswith("*/"):
                clean = text[3:-2].strip()
                comments.insert(0, clean)
            prev = prev.prev_sibling

        return "\n".join(comments) if comments else None

    def _extract_calls(self, node: Any, source_bytes: bytes) -> list[str]:
        """Extract all function/method call names made inside this function."""
        calls: list[str] = []
        self._collect_calls(node, source_bytes, calls)
        return list(dict.fromkeys(calls))

    def _collect_calls(self, node: Any, source_bytes: bytes, calls: list[str]) -> None:
        if node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            if fn_node:
                call_text = self._node_text(fn_node, source_bytes)
                name = call_text.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
                if name:
                    calls.append(name)

        for child in node.children:
            self._collect_calls(child, source_bytes, calls)

    @staticmethod
    def _node_text(node: Any, source_bytes: bytes) -> str:
        if not node:
            return ""
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()

    @staticmethod
    def _line_of(node: Any) -> int:
        return int(node.start_point[0]) + 1

    @staticmethod
    def _end_line_of(node: Any) -> int:
        return int(node.end_point[0]) + 1
