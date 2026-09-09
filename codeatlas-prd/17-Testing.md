# 17 — Testing

## Overview

CodeAtlas AI uses a multi-layer testing strategy: unit tests, integration tests, end-to-end tests, and AI-specific evaluation suites. Target overall coverage: **≥ 80%** on critical paths.

---

## Testing Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Unit | pytest + pytest-asyncio | Service business logic |
| Unit (Frontend) | Vitest + React Testing Library | React components |
| Integration | pytest + testcontainers | Service + real DB/cache |
| E2E | Playwright | Full UI flows |
| AI Evaluation | RAGAS / custom eval | RAG answer quality |
| Load | Locust | Performance under load |
| Security | Bandit + semgrep | Static analysis in CI |
| Contract | Schemathesis | OpenAPI contract testing |

---

## Unit Tests

### Backend (pytest)

```python
# tests/unit/ai_service/test_rag.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_service.rag.pipeline import RAGPipeline

@pytest.fixture
def mock_qdrant():
    client = AsyncMock()
    client.search.return_value = [
        MagicMock(
            payload={"file_path": "src/auth.py", "start_line": 10,
                     "end_line": 40, "content": "def authenticate():..."},
            score=0.92
        )
    ]
    return client

@pytest.fixture
def mock_neo4j():
    session = AsyncMock()
    session.run.return_value = AsyncMock(data=lambda: [])
    return session

@pytest.mark.asyncio
async def test_hybrid_retrieve_returns_results(mock_qdrant, mock_neo4j):
    pipeline = RAGPipeline(qdrant=mock_qdrant, neo4j=mock_neo4j)
    results = await pipeline.retrieve(
        query="how does authentication work",
        repo_id="test-repo-id"
    )
    assert len(results) > 0
    assert results[0]["file_path"] == "src/auth.py"
    mock_qdrant.search.assert_called_once()

@pytest.mark.asyncio
async def test_retrieve_respects_repo_filter(mock_qdrant, mock_neo4j):
    pipeline = RAGPipeline(qdrant=mock_qdrant, neo4j=mock_neo4j)
    await pipeline.retrieve("auth", repo_id="repo-123")
    call_kwargs = mock_qdrant.search.call_args
    assert call_kwargs.kwargs["query_filter"].must[0].match.value == "repo-123"
```

### Parser Unit Tests

```python
# tests/unit/parser/test_python_parser.py

from parser_service.parsers.python import PythonParser

def test_extracts_functions():
    source = '''
def greet(name: str) -> str:
    """Return greeting."""
    return f"Hello {name}"
'''
    parser = PythonParser()
    symbols = parser.parse(source, file_path="test.py")
    functions = [s for s in symbols if s.kind == "function"]
    assert len(functions) == 1
    assert functions[0].name == "greet"
    assert functions[0].start_line == 2
    assert functions[0].docstring == "Return greeting."

def test_extracts_classes_with_methods():
    source = '''
class UserService:
    def get_user(self, user_id: int) -> User:
        pass
'''
    parser = PythonParser()
    symbols = parser.parse(source, file_path="test.py")
    classes = [s for s in symbols if s.kind == "class"]
    methods = [s for s in symbols if s.kind == "method"]
    assert len(classes) == 1
    assert classes[0].name == "UserService"
    assert len(methods) == 1
    assert methods[0].parent_class == "UserService"
```

---

## Integration Tests

Integration tests use **testcontainers** to spin up real PostgreSQL, Redis, Qdrant, and Neo4j instances:

```python
# tests/integration/test_repo_ingestion.py

import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from httpx import AsyncClient

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

@pytest.fixture(scope="session")
def redis():
    with RedisContainer("redis:7-alpine") as r:
        yield r

@pytest.mark.asyncio
async def test_import_repository(postgres, redis, test_client: AsyncClient):
    # Login
    login_response = await test_client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword"
    })
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Import repository
    response = await test_client.post("/repos", headers=headers, json={
        "url": "https://github.com/octocat/Hello-World",
        "name": "hello-world"
    })
    assert response.status_code == 202
    repo_id = response.json()["id"]

    # Check status becomes "queued" or "running"
    status_response = await test_client.get(f"/repos/{repo_id}/status", headers=headers)
    assert status_response.json()["status"] in ["queued", "running", "complete"]
```

---

## End-to-End Tests (Playwright)

```typescript
// tests/e2e/chat.spec.ts

import { test, expect } from '@playwright/test';

test.describe('AI Chat', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Login
    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpassword');
    await page.click('[data-testid="login-btn"]');
    await expect(page).toHaveURL('/');
  });

  test('sends a message and receives streamed response with citations', async ({ page }) => {
    // Navigate to a repository's chat
    await page.goto('/repositories/test-repo-id/chat');

    // Type a question
    await page.fill('[data-testid="chat-input"]', 'How does authentication work?');
    await page.click('[data-testid="send-btn"]');

    // Wait for streaming response to complete
    await expect(page.locator('[data-testid="assistant-message"]')).toBeVisible({ timeout: 30000 });

    // Check that citations are present
    const citations = page.locator('[data-testid="citation"]');
    await expect(citations.first()).toBeVisible();

    // Verify citation contains file path
    const citationText = await citations.first().textContent();
    expect(citationText).toMatch(/\.py|\.ts|\.js/);
  });

  test('citation click opens code preview', async ({ page }) => {
    await page.goto('/repositories/test-repo-id/chat');
    await page.fill('[data-testid="chat-input"]', 'What is the main entry point?');
    await page.click('[data-testid="send-btn"]');

    await page.locator('[data-testid="citation"]').first().click();
    await expect(page.locator('[data-testid="code-preview"]')).toBeVisible();
  });
});
```

---

## AI Evaluation (RAGAS)

Automated evaluation of RAG quality using RAGAS framework:

```python
# tests/eval/test_rag_quality.py

from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness
)
from datasets import Dataset

EVAL_DATASET = [
    {
        "question": "How does the user authentication work?",
        "ground_truth": "The authenticate_user function in src/auth/service.py validates credentials using bcrypt password hashing and returns a JWT token.",
        "contexts": [...],  # retrieved chunks
        "answer": "..."     # LLM response
    },
    # ... more test cases
]

def test_rag_answer_relevancy():
    dataset = Dataset.from_list(EVAL_DATASET)
    results = evaluate(dataset, metrics=[answer_relevancy])
    assert results["answer_relevancy"] >= 0.90, \
        f"Answer relevancy {results['answer_relevancy']:.2f} below threshold 0.90"

def test_rag_faithfulness():
    dataset = Dataset.from_list(EVAL_DATASET)
    results = evaluate(dataset, metrics=[faithfulness])
    assert results["faithfulness"] >= 0.85, \
        f"Faithfulness {results['faithfulness']:.2f} below threshold 0.85"

def test_rag_context_recall():
    dataset = Dataset.from_list(EVAL_DATASET)
    results = evaluate(dataset, metrics=[context_recall])
    assert results["context_recall"] >= 0.80
```

---

## Load Tests (Locust)

```python
# tests/load/locustfile.py

from locust import HttpUser, task, between

class CodeAtlasUser(HttpUser):
    wait_time = between(1, 5)
    token: str = ""

    def on_start(self):
        response = self.client.post("/api/v1/auth/login", json={
            "email": "loadtest@example.com",
            "password": "loadtest"
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def search_code(self):
        self.client.get(
            "/api/v1/search?q=authentication&repo_id=test-repo",
            headers=self.headers
        )

    @task(2)
    def get_repository(self):
        self.client.get("/api/v1/repos/test-repo-id", headers=self.headers)

    @task(1)
    def chat_message(self):
        self.client.post("/api/v1/ai/chat", headers=self.headers, json={
            "repo_id": "test-repo-id",
            "message": "What does the main function do?",
            "stream": False
        })
```

**Load test targets:**
- 100 concurrent users: P95 latency < 500ms for search
- 50 concurrent chat users: P95 latency < 5s (local LLM)
- 0% error rate under normal load

---

## CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -r requirements-dev.txt
      - run: pytest tests/unit --cov --cov-report=xml -q
      - uses: codecov/codecov-action@v4

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose -f docker-compose.test.yml up -d
      - run: pytest tests/integration -q --timeout=120
      - run: docker compose -f docker-compose.test.yml down

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test tests/e2e
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit semgrep
      - run: bandit -r services/ -ll -q
      - run: semgrep --config auto services/ --error
```

---

## Coverage Requirements

| Service | Minimum Coverage |
|---------|----------------|
| Auth Service | 90% |
| AI Service (RAG pipeline) | 85% |
| Parser Service | 85% |
| Security Scanner | 80% |
| Repo Service | 80% |
| All other services | 75% |
| Frontend components | 70% |
