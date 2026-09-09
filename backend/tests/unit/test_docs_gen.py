"""Unit tests for the docs_gen modules.

All LLM calls are mocked — no external services required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.docs_gen.exporters import (
    _basic_md_to_html,
    _md_table_to_confluence,
    to_confluence_xml,
    to_html,
    to_notion_blocks,
)


# ── HTML exporter ──────────────────────────────────────────────────────────────


class TestToHtml:
    def test_wraps_in_html_document(self) -> None:
        html = to_html("# Hello\n\nWorld", title="Test Doc")
        assert "<!DOCTYPE html>" in html
        assert "<title>Test Doc</title>" in html
        assert "<body>" in html

    def test_heading_converted(self) -> None:
        html = to_html("# My Heading")
        assert "My Heading" in html

    def test_escapes_title(self) -> None:
        html = to_html("text", title="<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_content(self) -> None:
        html = to_html("")
        assert "<!DOCTYPE html>" in html


class TestBasicMdToHtml:
    def test_h1(self) -> None:
        assert "<h1>Foo</h1>" in _basic_md_to_html("# Foo")

    def test_bold(self) -> None:
        assert "<strong>bold</strong>" in _basic_md_to_html("**bold**")

    def test_italic(self) -> None:
        assert "<em>italic</em>" in _basic_md_to_html("*italic*")

    def test_code_block(self) -> None:
        md = "```python\ndef foo(): pass\n```"
        assert "<pre><code>" in _basic_md_to_html(md)


# ── Confluence XML exporter ────────────────────────────────────────────────────


class TestToConfluenceXml:
    def test_heading_converted(self) -> None:
        xml = to_confluence_xml("# Section Title")
        assert "<h1>Section Title</h1>" in xml

    def test_h2_heading(self) -> None:
        xml = to_confluence_xml("## Sub Section")
        assert "<h2>Sub Section</h2>" in xml

    def test_bullet_list(self) -> None:
        xml = to_confluence_xml("- Item one\n- Item two")
        assert "<ul>" in xml
        assert "<li>" in xml
        assert "Item one" in xml

    def test_code_block(self) -> None:
        xml = to_confluence_xml("```python\ndef foo(): pass\n```")
        assert "ac:structured-macro" in xml
        assert "code" in xml
        assert "def foo(): pass" in xml

    def test_blockquote(self) -> None:
        xml = to_confluence_xml("> A quoted line")
        assert "<blockquote>" in xml
        assert "A quoted line" in xml

    def test_paragraph(self) -> None:
        xml = to_confluence_xml("Some plain text here.")
        assert "<p>Some plain text here.</p>" in xml


class TestMdTableToConfluence:
    def test_simple_table(self) -> None:
        rows = [
            "| Name | Age |",
            "|------|-----|",
            "| Alice | 30 |",
        ]
        xml = _md_table_to_confluence(rows)
        assert "<table>" in xml
        assert "<th>Name</th>" in xml
        assert "Alice" in xml

    def test_empty_rows(self) -> None:
        assert _md_table_to_confluence([]) == ""


# ── Notion blocks exporter ────────────────────────────────────────────────────


class TestToNotionBlocks:
    def test_heading_1(self) -> None:
        blocks = to_notion_blocks("# Title")
        assert blocks[0]["type"] == "heading_1"
        assert blocks[0]["heading_1"]["rich_text"][0]["text"]["content"] == "Title"

    def test_heading_2(self) -> None:
        blocks = to_notion_blocks("## Subtitle")
        assert blocks[0]["type"] == "heading_2"

    def test_heading_capped_at_3(self) -> None:
        blocks = to_notion_blocks("#### Deep heading")
        assert blocks[0]["type"] == "heading_3"

    def test_bullet_item(self) -> None:
        blocks = to_notion_blocks("- List item")
        assert blocks[0]["type"] == "bulleted_list_item"
        assert "List item" in blocks[0]["bulleted_list_item"]["rich_text"][0]["text"]["content"]

    def test_code_block(self) -> None:
        blocks = to_notion_blocks("```python\nprint('hello')\n```")
        code_blocks = [b for b in blocks if b["type"] == "code"]
        assert len(code_blocks) == 1
        assert "python" in code_blocks[0]["code"]["language"]

    def test_divider(self) -> None:
        blocks = to_notion_blocks("---")
        assert blocks[0]["type"] == "divider"

    def test_paragraph(self) -> None:
        blocks = to_notion_blocks("Some text here.")
        assert blocks[0]["type"] == "paragraph"
        assert "Some text here." in blocks[0]["paragraph"]["rich_text"][0]["text"]["content"]

    def test_mixed_content(self) -> None:
        md = "# Title\n\nSome text.\n\n- Item 1\n- Item 2\n\n---\n\n```py\ncode\n```"
        blocks = to_notion_blocks(md)
        types = [b["type"] for b in blocks]
        assert "heading_1" in types
        assert "bulleted_list_item" in types
        assert "divider" in types
        assert "code" in types

    def test_empty_markdown(self) -> None:
        blocks = to_notion_blocks("")
        assert blocks == []


# ── Readme generator (mocked LLM) ────────────────────────────────────────────


class TestReadmeGenerator:
    def test_generate_readme_calls_llm(self) -> None:
        with patch("app.docs_gen.readme.call_llm", return_value="# My README\n\nContent.") as mock_llm:
            from app.docs_gen.readme import generate_readme
            result = generate_readme({
                "repo_name": "TestRepo",
                "description": "A test repo",
                "primary_language": "python",
                "languages": ["python"],
                "tech_stack": ["FastAPI", "PostgreSQL"],
                "license": "MIT",
                "file_tree": "src/\n  main.py\n",
                "package_files": "pyproject.toml",
                "module_summaries": "- src/: 10 symbols",
                "infra_info": "Docker Compose",
            })
            mock_llm.assert_called_once()
            assert "README" in result

    def test_generate_readme_uses_repo_name(self) -> None:
        with patch("app.docs_gen.readme.call_llm") as mock_llm:
            mock_llm.return_value = "# SpecialRepo\n"
            from app.docs_gen.readme import generate_readme
            generate_readme({"repo_name": "SpecialRepo"})
            call_args = mock_llm.call_args[0]
            # The user prompt (4th arg) should contain the repo name
            assert "SpecialRepo" in call_args[3]


# ── ADR generator (mocked LLM) ────────────────────────────────────────────────


class TestAdrGenerator:
    def test_detect_tech_decisions(self) -> None:
        from app.docs_gen.adr import _detect_tech_decisions
        symbols = [
            {"file_path": "app/workers/celery_app.py"},
            {"file_path": "app/models/user.py"},
        ]
        decisions = _detect_tech_decisions(symbols, ["FastAPI", "PostgreSQL"])
        assert any("FastAPI" in d or "fastapi" in d.lower() for d in decisions)

    def test_generate_adrs_calls_llm(self) -> None:
        with patch("app.docs_gen.adr.call_llm", return_value="# ADR-1: Use PostgreSQL\n") as mock_llm:
            from app.docs_gen.adr import generate_adrs
            result = generate_adrs("TestRepo", {"tech_stack": ["PostgreSQL", "Redis"]})
            mock_llm.assert_called_once()
            assert "ADR" in result


# ── API reference generator (mocked LLM) ─────────────────────────────────────


class TestApiReferenceGenerator:
    def test_extract_route_symbols_filters_by_name(self) -> None:
        from app.docs_gen.api_reference import _extract_route_symbols
        symbols = [
            {"name": "login_endpoint", "symbol_kind": "function", "file_path": "api/auth.py"},
            {"name": "calculate_total", "symbol_kind": "function", "file_path": "utils/math.py"},
            {"name": "get_users", "symbol_kind": "function", "file_path": "api/users.py"},
        ]
        result = _extract_route_symbols(symbols)
        names = [s["name"] for s in result]
        assert "login_endpoint" in names
        assert "get_users" in names
        assert "calculate_total" not in names

    def test_infer_framework_fastapi(self) -> None:
        from app.docs_gen.api_reference import _infer_framework
        symbols = [
            {"file_path": "app/api/v1/router.py", "qualified_name": "api_router"},
        ]
        fw = _infer_framework(symbols)
        assert fw == "FastAPI"

    def test_no_routes_returns_stub(self) -> None:
        from app.docs_gen.api_reference import generate_api_reference
        result = generate_api_reference("EmptyRepo", [])
        assert "No API routes detected" in result
