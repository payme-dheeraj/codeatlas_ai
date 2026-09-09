"""Tree-sitter based Java source code parser."""

from __future__ import annotations

from typing import Any

from app.parser.base import BaseLanguageParser, SymbolData


class JavaParser(BaseLanguageParser):
    """Extracts symbols from Java source using Tree-sitter.

    Extracted symbol kinds:
    - ``class``      — class declarations
    - ``interface``  — interface declarations
    - ``enum``       — enum declarations
    - ``method``     — method declarations
    - ``import``     — import declarations
    - ``constant``   — static final field declarations
    """

    language_name = "java"
    _grammar: Any = None

    @classmethod
    def _load_grammar(cls) -> Any:
        """Load the Tree-sitter Java grammar.

        Returns:
            tree_sitter.Language instance for Java.
        """
        import tree_sitter_java as tsjava
        from tree_sitter import Language

        return Language(tsjava.language())

    def parse(self, source: str, file_path: str) -> list[SymbolData]:
        """Parse Java source and return extracted symbols.

        Args:
            source: Full Java source text.
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
        for child in node.children:
            t = child.type
            if t == "import_declaration":
                self._process_import(child, source_bytes, symbols)
            elif t in ("class_declaration", "record_declaration"):
                self._process_class(child, source_bytes, symbols)
            elif t == "interface_declaration":
                self._process_interface(child, source_bytes, symbols)
            elif t == "enum_declaration":
                self._process_enum(child, source_bytes, symbols)
            elif t == "method_declaration":
                self._process_method(child, source_bytes, symbols, parent_class)
            elif t == "field_declaration":
                self._process_field(child, source_bytes, symbols, parent_class)
            elif t == "program":
                self._walk(child, source_bytes, symbols, parent_class)

    def _process_class(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_name(node, source_bytes)
        if not name:
            return
        doc = self._extract_javadoc(node, source_bytes)
        annotations = self._extract_annotations(node, source_bytes)

        # Collect superclass / interfaces
        superclass: str | None = None
        interfaces: list[str] = []
        for child in node.children:
            if child.type == "superclass":
                superclass = self._node_text(child, source_bytes).replace("extends ", "")
            elif child.type == "super_interfaces":
                interfaces.append(
                    self._node_text(child, source_bytes).replace("implements ", "")
                )

        symbols.append(
            SymbolData(
                name=name,
                qualified_name=name,
                symbol_kind="class",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
                decorators=annotations,
                extras={
                    "superclass": superclass,
                    "interfaces": interfaces,
                },
            )
        )

        # Recurse into class body
        body = self._first_child_type(node, "class_body")
        if body:
            self._walk(body, source_bytes, symbols, name)

    def _process_interface(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_name(node, source_bytes)
        if not name:
            return
        doc = self._extract_javadoc(node, source_bytes)
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

    def _process_enum(
        self, node: Any, source_bytes: bytes, symbols: list[SymbolData]
    ) -> None:
        name = self._get_name(node, source_bytes)
        if not name:
            return
        members: list[str] = []
        body = self._first_child_type(node, "enum_body")
        if body:
            for child in body.children:
                if child.type == "enum_constant":
                    members.append(self._get_name(child, source_bytes))
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

    def _process_method(
        self,
        node: Any,
        source_bytes: bytes,
        symbols: list[SymbolData],
        parent_class: str | None,
    ) -> None:
        name = self._get_name(node, source_bytes)
        if not name:
            return
        qualified = f"{parent_class}.{name}" if parent_class else name
        doc = self._extract_javadoc(node, source_bytes)
        annotations = self._extract_annotations(node, source_bytes)
        sig = self._build_java_signature(node, source_bytes, name)
        calls = self._extract_calls(node, source_bytes)

        modifiers: list[str] = []
        for child in node.children:
            if child.type == "modifiers":
                modifiers = self._node_text(child, source_bytes).split()

        symbols.append(
            SymbolData(
                name=name,
                qualified_name=qualified,
                symbol_kind="method",
                start_line=self._line_of(node),
                end_line=self._end_line_of(node),
                docstring=doc,
                signature=sig,
                parent_name=parent_class,
                decorators=annotations,
                calls=calls,
                extras={"modifiers": modifiers},
            )
        )

    def _process_field(
        self,
        node: Any,
        source_bytes: bytes,
        symbols: list[SymbolData],
        parent_class: str | None,
    ) -> None:
        """Extract static final fields as constants."""
        modifiers_node = self._first_child_type(node, "modifiers")
        if modifiers_node is None:
            return
        mods = self._node_text(modifiers_node, source_bytes)
        if "static" not in mods or "final" not in mods:
            return

        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = self._node_text(name_node, source_bytes)
                    qualified = f"{parent_class}.{name}" if parent_class else name
                    symbols.append(
                        SymbolData(
                            name=name,
                            qualified_name=qualified,
                            symbol_kind="constant",
                            start_line=self._line_of(node),
                            end_line=self._end_line_of(node),
                            parent_name=parent_class,
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

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _get_name(self, node: Any, source_bytes: bytes) -> str:
        for child in node.children:
            if child.type == "identifier":
                return self._node_text(child, source_bytes)
        return ""

    def _first_child_type(self, node: Any, type_: str) -> Any | None:
        for child in node.children:
            if child.type == type_:
                return child
        return None

    def _extract_javadoc(self, node: Any, source_bytes: bytes) -> str | None:
        prev = node.prev_sibling
        if prev and prev.type in ("block_comment", "line_comment"):
            raw = self._node_text(prev, source_bytes)
            if raw.startswith("/**") or raw.startswith("//"):
                return self._clean_docstring(raw)
        return None

    def _extract_annotations(self, node: Any, source_bytes: bytes) -> list[str]:
        result: list[str] = []
        for child in node.children:
            if child.type == "modifiers":
                for sub in child.children:
                    if sub.type in ("annotation", "marker_annotation"):
                        result.append(self._node_text(sub, source_bytes))
        return result

    def _build_java_signature(
        self, node: Any, source_bytes: bytes, name: str
    ) -> str | None:
        ret_type = None
        params = None
        for child in node.children:
            if child.type in (
                "void_type",
                "integral_type",
                "floating_point_type",
                "boolean_type",
                "type_identifier",
                "generic_type",
                "array_type",
            ):
                ret_type = self._node_text(child, source_bytes)
            elif child.type == "formal_parameters":
                params = self._node_text(child, source_bytes)
        if params is None:
            return None
        ret = f"{ret_type} " if ret_type else ""
        return f"{ret}{name}{params}"

    def _extract_calls(self, node: Any, source_bytes: bytes) -> list[str]:
        calls: set[str] = set()

        def _rec(n: Any) -> None:
            if n.type == "method_invocation":
                name_node = n.child_by_field_name("name")
                if name_node:
                    calls.add(self._node_text(name_node, source_bytes))
            for c in n.children:
                _rec(c)

        _rec(node)
        return sorted(calls)
