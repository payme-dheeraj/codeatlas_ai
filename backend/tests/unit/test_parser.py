"""Unit tests for parser subsystem.

Tests the classifier, language parsers, and Neo4j writer utilities
in complete isolation — no DB, no MinIO, no Neo4j required.
"""

from __future__ import annotations

import pytest

from app.parser.base import SymbolData
from app.parser.classifier import classify_file, detect_language, should_skip_file
from app.parser.graph.neo4j_writer import _file_node_id, _symbol_node_id


# ── Classifier tests ───────────────────────────────────────────────────────────


class TestClassifyFile:
    def test_test_directory(self) -> None:
        assert classify_file("tests/unit/test_auth.py") == "test"

    def test_spec_file(self) -> None:
        assert classify_file("src/auth.spec.ts") == "test"

    def test_migration_file(self) -> None:
        assert classify_file("alembic/versions/0001_initial.py") == "migration"

    def test_config_file(self) -> None:
        assert classify_file("app/core/config.py") == "config"

    def test_settings_file(self) -> None:
        assert classify_file("settings.py") == "config"

    def test_worker_directory(self) -> None:
        assert classify_file("workers/tasks/repo_tasks.py") == "worker"

    def test_controller_directory(self) -> None:
        assert classify_file("controllers/auth_controller.py") == "controller"

    def test_repository_directory(self) -> None:
        assert classify_file("repositories/user_repository.py") == "repository"

    def test_schema_directory(self) -> None:
        assert classify_file("schemas/repository.py") == "schema"

    def test_model_directory(self) -> None:
        assert classify_file("models/user.py") == "model"

    def test_service_directory(self) -> None:
        assert classify_file("services/auth_service.py") == "service"

    def test_generic_fallback(self) -> None:
        assert classify_file("random/unknown.py") == "generic"

    def test_import_heuristic_fastapi(self) -> None:
        source = "from fastapi import APIRouter, Depends\nrouter = APIRouter()"
        assert classify_file("app/routes.py", source) == "controller"

    def test_import_heuristic_sqlalchemy(self) -> None:
        source = "from sqlalchemy import Column\nfrom sqlalchemy.orm import declarative_base"
        assert classify_file("app/entity.py", source) == "model"


class TestDetectLanguage:
    def test_python(self) -> None:
        assert detect_language("app/main.py") == "python"

    def test_typescript(self) -> None:
        assert detect_language("src/index.ts") == "typescript"

    def test_tsx(self) -> None:
        assert detect_language("components/Button.tsx") == "typescript"

    def test_javascript(self) -> None:
        assert detect_language("src/app.js") == "javascript"

    def test_jsx(self) -> None:
        assert detect_language("components/App.jsx") == "javascript"

    def test_java(self) -> None:
        assert detect_language("src/Main.java") == "java"

    def test_go(self) -> None:
        assert detect_language("cmd/main.go") == "go"

    def test_rust(self) -> None:
        assert detect_language("src/lib.rs") == "rust"
        assert detect_language("src/main.rs") == "rust"

    def test_unknown(self) -> None:
        assert detect_language("README.md") is None

    def test_yaml_none(self) -> None:
        assert detect_language("config.yaml") is None


class TestShouldSkipFile:
    def test_node_modules(self) -> None:
        assert should_skip_file("node_modules/lodash/index.js") is True

    def test_pycache(self) -> None:
        assert should_skip_file("app/__pycache__/main.cpython-312.pyc") is True

    def test_git_dir(self) -> None:
        assert should_skip_file(".git/HEAD") is True

    def test_minified_js(self) -> None:
        assert should_skip_file("dist/bundle.min.js") is True

    def test_normal_file(self) -> None:
        assert should_skip_file("app/services/auth_service.py") is False

    def test_test_file_not_skipped(self) -> None:
        assert should_skip_file("tests/test_auth.py") is False


# ── Python parser tests ────────────────────────────────────────────────────────


class TestPythonParser:
    """Tests for PythonParser using real Tree-sitter grammar."""

    @pytest.fixture
    def parser(self):
        pytest.importorskip("tree_sitter_python", reason="tree-sitter-python not installed")
        from app.parser.languages.python import PythonParser
        return PythonParser()

    def test_parses_function(self, parser) -> None:
        source = '''def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}"
'''
        symbols = parser.parse(source, "greet.py")
        funcs = [s for s in symbols if s.symbol_kind == "function"]
        assert any(s.name == "hello" for s in funcs)

    def test_parses_class_and_methods(self, parser) -> None:
        source = '''class AuthService:
    """Auth logic."""

    def login(self, email: str) -> str:
        return email

    def logout(self) -> None:
        pass
'''
        symbols = parser.parse(source, "services/auth.py")
        classes = [s for s in symbols if s.symbol_kind == "class"]
        methods = [s for s in symbols if s.symbol_kind == "method"]
        assert any(s.name == "AuthService" for s in classes)
        assert any(s.name == "login" for s in methods)
        assert any(s.name == "logout" for s in methods)

    def test_extracts_docstring(self, parser) -> None:
        source = '''def greet():
    """This is a greeting function."""
    pass
'''
        symbols = parser.parse(source, "greet.py")
        assert symbols[0].docstring == "This is a greeting function."

    def test_extracts_decorator(self, parser) -> None:
        source = '''@router.get("/")
@requires_auth
def index():
    pass
'''
        symbols = parser.parse(source, "routes.py")
        funcs = [s for s in symbols if s.symbol_kind == "function"]
        assert len(funcs) == 1
        assert "router.get" in funcs[0].decorators or "requires_auth" in funcs[0].decorators

    def test_parses_import(self, parser) -> None:
        source = "from fastapi import APIRouter, Depends\n"
        symbols = parser.parse(source, "main.py")
        imports = [s for s in symbols if s.symbol_kind == "import"]
        assert len(imports) == 1

    def test_extracts_constant(self, parser) -> None:
        source = "MAX_RETRIES = 3\nTIMEOUT = 30\n"
        symbols = parser.parse(source, "config.py")
        constants = [s for s in symbols if s.symbol_kind == "constant"]
        names = {s.name for s in constants}
        assert "MAX_RETRIES" in names
        assert "TIMEOUT" in names

    def test_method_qualified_name(self, parser) -> None:
        source = '''class Foo:
    def bar(self):
        pass
'''
        symbols = parser.parse(source, "foo.py")
        methods = [s for s in symbols if s.symbol_kind == "method"]
        assert methods[0].qualified_name == "Foo.bar"
        assert methods[0].parent_name == "Foo"

    def test_async_function_flagged(self, parser) -> None:
        source = "async def fetch_data():\n    pass\n"
        symbols = parser.parse(source, "tasks.py")
        funcs = [s for s in symbols if s.symbol_kind == "function"]
        assert funcs[0].extras.get("is_async") is True

    def test_empty_source(self, parser) -> None:
        symbols = parser.parse("", "empty.py")
        assert symbols == []

    def test_calls_extracted(self, parser) -> None:
        source = '''def process():
    result = validate()
    send_email(result)
    return result
'''
        symbols = parser.parse(source, "proc.py")
        funcs = [s for s in symbols if s.symbol_kind == "function"]
        calls = funcs[0].calls
        assert "validate" in calls
        assert "send_email" in calls


# ── Neo4j writer utilities ─────────────────────────────────────────────────────


class TestNeo4jWriterUtils:
    def test_file_node_id_deterministic(self) -> None:
        repo_id = "550e8400-e29b-41d4-a716-446655440000"
        path = "src/main.py"
        assert _file_node_id(repo_id, path) == _file_node_id(repo_id, path)

    def test_file_node_id_unique_per_path(self) -> None:
        repo_id = "550e8400-e29b-41d4-a716-446655440000"
        assert _file_node_id(repo_id, "a.py") != _file_node_id(repo_id, "b.py")

    def test_symbol_node_id_deterministic(self) -> None:
        repo_id = "550e8400-e29b-41d4-a716-446655440000"
        assert (
            _symbol_node_id(repo_id, "a.py", "function", "hello")
            == _symbol_node_id(repo_id, "a.py", "function", "hello")
        )

    def test_symbol_node_id_unique_per_kind(self) -> None:
        repo_id = "550e8400-e29b-41d4-a716-446655440000"
        assert (
            _symbol_node_id(repo_id, "a.py", "function", "foo")
            != _symbol_node_id(repo_id, "a.py", "class", "foo")
        )


# ── Rust parser tests ──────────────────────────────────────────────────────────


class TestRustParser:
    """Tests for RustParser using real Tree-sitter grammar."""

    @pytest.fixture
    def parser(self):
        pytest.importorskip("tree_sitter_rust", reason="tree-sitter-rust not installed")
        from app.parser.languages.rust import RustParser
        return RustParser()

    def test_parses_function(self, parser) -> None:
        source = """pub fn calculate_sum(a: i32, b: i32) -> i32 {
    a + b
}
"""
        symbols = parser.parse(source, "calc.rs")
        funcs = [s for s in symbols if s.symbol_kind == "function"]
        assert any(s.name == "calculate_sum" for s in funcs)

    def test_parses_struct_and_impl(self, parser) -> None:
        source = """pub struct Server {
    port: u16,
}

impl Server {
    pub fn new(port: u16) -> Self {
        Server { port }
    }
}
"""
        symbols = parser.parse(source, "server.rs")
        structs = [s for s in symbols if s.symbol_kind == "struct"]
        methods = [s for s in symbols if s.symbol_kind == "method"]
        assert any(s.name == "Server" for s in structs)
        assert any(s.name == "new" and s.parent_name == "Server" for s in methods)

    def test_parses_enum_and_trait(self, parser) -> None:
        source = """pub enum Status {
    Active,
    Inactive,
}

pub trait Greeter {
    fn greet(&self) -> String;
}
"""
        symbols = parser.parse(source, "types.rs")
        enums = [s for s in symbols if s.symbol_kind == "enum"]
        traits = [s for s in symbols if s.symbol_kind == "trait"]
        assert any(s.name == "Status" for s in enums)
        assert any(s.name == "Greeter" for s in traits)

    def test_parses_use_declaration(self, parser) -> None:
        source = "use std::collections::HashMap;\n"
        symbols = parser.parse(source, "main.rs")
        imports = [s for s in symbols if s.symbol_kind == "import"]
        assert len(imports) == 1
        assert "HashMap" in imports[0].name


class TestParserRegistry:
    def test_registry_contains_supported_languages(self) -> None:
        from app.parser.registry import get_parser, supported_languages

        languages = supported_languages()
        assert "python" in languages
        assert "typescript" in languages
        assert "javascript" in languages
        assert "go" in languages
        assert "java" in languages
        assert "rust" in languages

    def test_get_parser_returns_correct_instance(self) -> None:
        pytest.importorskip("tree_sitter_rust", reason="tree-sitter-rust not installed")
        from app.parser.languages.rust import RustParser
        from app.parser.registry import get_parser

        parser = get_parser("rust")
        assert isinstance(parser, RustParser)

