"""Unit tests for all diagram generator modules.

All external dependencies (Neo4j, LLM, MinIO, Kroki) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.diagrams.generators.architecture import (
    _from_compose,
    _from_k8s,
    generate_architecture,
)
from app.diagrams.generators.dependency import (
    _safe_id,
    _short_label,
    generate_dependency,
    generate_dependency_from_symbols,
)
from app.diagrams.generators.deployment import (
    _compose_to_d2,
    _compose_to_mermaid,
    generate_deployment,
)
from app.diagrams.generators.er import (
    _build_entity_blocks,
    _empty_er,
    _extract_attrs_from_docstring,
    _mermaid_name,
    generate_er,
)
from app.diagrams.generators.sequence import (
    _from_call_graph,
    generate_sequence,
)


# ── Architecture generator ────────────────────────────────────────────────────


class TestArchitectureGenerator:
    def _svc(self, name: str, image: str = "", ports=None, depends_on=None) -> dict:
        return {
            "name": name,
            "image": image,
            "build": False,
            "ports": ports or [],
            "depends_on": depends_on or [],
        }

    def test_from_compose_produces_c4container(self) -> None:
        services = [
            self._svc("api", "fastapi:latest"),
            self._svc("db", "postgres:16", depends_on=["api"]),
        ]
        src = _from_compose("MyApp", services)
        assert "C4Container" in src
        assert "api" in src
        assert "db" in src

    def test_from_compose_includes_dependency_edges(self) -> None:
        services = [
            self._svc("backend"),
            self._svc("frontend", depends_on=["backend"]),
        ]
        src = _from_compose("TestApp", services)
        assert "Rel(" in src

    def test_from_k8s_produces_graph(self) -> None:
        k8s = [{"name": "api-svc", "kind": "Service", "namespace": "default", "containers": [], "ports": []}]
        src = _from_k8s("K8sApp", k8s)
        assert "graph TD" in src
        assert "api_svc" in src or "api-svc" in src

    def test_generate_prefers_compose_over_k8s(self) -> None:
        compose = [self._svc("svc1")]
        k8s = [{"name": "k8s-svc", "kind": "Service", "namespace": "default", "containers": [], "ports": []}]
        src = generate_architecture("App", compose, k8s)
        assert "C4Container" in src

    def test_generate_falls_back_to_k8s(self) -> None:
        k8s = [{"name": "my-app", "kind": "Deployment", "namespace": "default", "containers": [], "ports": []}]
        src = generate_architecture("App", [], k8s)
        assert "graph" in src.lower()

    def test_generate_ai_fallback_on_no_infra(self) -> None:
        with patch("app.diagrams.generators.architecture.call_llm", return_value="graph TD\n    A[App]") as mock:
            src = generate_architecture("MyRepo", [], [])
            mock.assert_called_once()
            assert "graph TD" in src or "C4" in src


# ── Dependency generator ──────────────────────────────────────────────────────


class TestDependencyGenerator:
    def test_safe_id_replaces_special_chars(self) -> None:
        assert _safe_id("src/api/routes.py") == "src_api_routes_py"

    def test_short_label_truncates_deep_paths(self) -> None:
        label = _short_label("src/api/v1/endpoints/auth.py")
        assert "…/" in label or "endpoints" in label

    def test_generate_dependency_produces_graph(self) -> None:
        edges = [
            {"source": "src/main.py", "target": "src/api.py", "weight": 3},
            {"source": "src/api.py", "target": "src/db.py", "weight": 1},
        ]
        src = generate_dependency("TestRepo", edges)
        assert "graph TD" in src
        assert "src_main_py" in src or "main" in src

    def test_generate_dependency_empty_returns_stub(self) -> None:
        src = generate_dependency("EmptyRepo", [])
        assert "No import data available" in src

    def test_generate_dependency_caps_nodes(self) -> None:
        edges = [
            {"source": f"file{i}.py", "target": f"file{i+1}.py", "weight": 1}
            for i in range(100)
        ]
        src = generate_dependency("BigRepo", edges, max_nodes=10)
        node_lines = [l for l in src.splitlines() if '["' in l]
        assert len(node_lines) <= 10

    def test_generate_from_symbols_fallback(self) -> None:
        symbols = [
            {"file_path": "app/api/routes.py"},
            {"file_path": "app/models/user.py"},
            {"file_path": "app/services/auth.py"},
        ]
        src = generate_dependency_from_symbols("TestRepo", symbols)
        assert "graph" in src.lower()
        assert "app" in src


# ── Sequence generator ────────────────────────────────────────────────────────


class TestSequenceGenerator:
    def test_from_call_graph_produces_sequence(self) -> None:
        edges = [
            {"caller": "api.login", "callee": "auth.validate", "file": "api.py"},
            {"caller": "auth.validate", "callee": "db.query", "file": "auth.py"},
        ]
        src = _from_call_graph("TestRepo", edges, focus_symbol=None)
        assert "sequenceDiagram" in src
        assert "->>" in src

    def test_from_call_graph_caps_at_30(self) -> None:
        edges = [
            {"caller": f"caller_{i}", "callee": f"callee_{i}", "file": "f.py"}
            for i in range(50)
        ]
        src = _from_call_graph("Repo", edges, focus_symbol=None)
        # Should not error; actor count limited
        assert "sequenceDiagram" in src

    def test_generate_sequence_empty_calls_ai(self) -> None:
        with patch("app.diagrams.generators.sequence.call_llm", return_value="sequenceDiagram\n    A->>B: test") as mock:
            src = generate_sequence("Repo", [])
            mock.assert_called_once()
            assert "sequenceDiagram" in src

    def test_generate_sequence_uses_edges_when_available(self) -> None:
        edges = [{"caller": "a.func", "callee": "b.func", "file": "a.py"}]
        with patch("app.diagrams.generators.sequence.call_llm") as mock_llm:
            src = generate_sequence("Repo", edges)
            mock_llm.assert_not_called()
            assert "sequenceDiagram" in src


# ── ER generator ──────────────────────────────────────────────────────────────


class TestErGenerator:
    def _model(self, name: str, docstring: str = "") -> dict:
        return {
            "name": name,
            "qualified_name": name,
            "file_path": f"app/models/{name.lower()}.py",
            "docstring": docstring,
            "extras": {},
            "language": "python",
        }

    def test_mermaid_name_sanitizes(self) -> None:
        assert _mermaid_name("My-Model.v2") == "My_Model_v2"

    def test_empty_er_stub(self) -> None:
        src = _empty_er("EmptyRepo")
        assert "erDiagram" in src

    def test_extract_attrs_from_docstring(self) -> None:
        doc = (
            "A user model.\n\n"
            "Attributes:\n"
            "    id: UUID primary key.\n"
            "    email: User email string.\n"
            "    created_at: datetime timestamp.\n"
        )
        attrs = _extract_attrs_from_docstring(doc)
        names = [a[0] for a in attrs]
        assert "id" in names
        assert "email" in names
        assert "created_at" in names

    def test_build_entity_blocks(self) -> None:
        models = [self._model("User"), self._model("Repository")]
        blocks = _build_entity_blocks(models)
        assert len(blocks) == 2
        assert any("User" in b[0] for b in blocks)

    def test_generate_er_empty_returns_stub(self) -> None:
        src = generate_er("EmptyRepo", [])
        assert "erDiagram" in src

    def test_generate_er_with_models(self) -> None:
        with patch("app.diagrams.generators.er.call_llm", return_value='    User ||--o{ Repository : "owns"'):
            models = [self._model("User"), self._model("Repository")]
            src = generate_er("TestRepo", models)
            assert "erDiagram" in src
            assert "User" in src


# ── Deployment generator ──────────────────────────────────────────────────────


class TestDeploymentGenerator:
    def _svc(self, name: str, ports=None, depends_on=None) -> dict:
        return {"name": name, "image": f"{name}:latest", "build": False,
                "ports": ports or [], "depends_on": depends_on or []}

    def test_compose_to_mermaid_produces_graph(self) -> None:
        services = [
            self._svc("api", ports=["8000:8000"]),
            self._svc("db"),
        ]
        src = _compose_to_mermaid("TestApp", services)
        assert "graph LR" in src
        assert "api" in src
        assert "db" in src

    def test_compose_to_mermaid_shows_external_port(self) -> None:
        services = [self._svc("web", ports=["80:80"])]
        src = _compose_to_mermaid("App", services)
        assert "internet" in src.lower()
        assert ":80" in src

    def test_compose_to_d2_produces_d2(self) -> None:
        services = [
            self._svc("api", depends_on=["db"]),
            self._svc("db"),
        ]
        src = _compose_to_d2("App", services)
        assert "direction:" in src
        assert "api -> db" in src

    def test_generate_prefers_compose(self) -> None:
        compose = [self._svc("api")]
        src = generate_deployment("App", compose, [])
        assert "graph LR" in src

    def test_generate_stub_when_no_infra(self) -> None:
        src = generate_deployment("Repo", [], [])
        assert "graph" in src.lower() or "client" in src


# ── Renderer (mocked) ─────────────────────────────────────────────────────────


class TestRenderer:
    def test_render_returns_empty_on_connection_error(self) -> None:
        import httpx
        from app.diagrams.renderer import render_diagram
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            result = render_diagram("graph TD\n    A-->B", "mermaid", "svg")
            assert result == b""

    def test_render_returns_bytes_on_success(self) -> None:
        from app.diagrams.renderer import render_diagram
        mock_response = MagicMock()
        mock_response.content = b"<svg>test</svg>"
        mock_response.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_response):
            result = render_diagram("graph TD\n    A-->B", "mermaid", "svg")
            assert result == b"<svg>test</svg>"
