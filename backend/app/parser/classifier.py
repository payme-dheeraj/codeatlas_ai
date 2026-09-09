"""File type classifier for source code files.

Classifies a file into one of the following roles based on its path,
name patterns, and a secondary heuristic pass over extracted imports/symbols:

    controller  — HTTP route handlers / view functions
    service     — Business logic layer
    model       — ORM models / database schemas / entities
    repository  — Data access layer (DAOs, repositories)
    schema      — Validation schemas (Pydantic, Zod, Joi, Marshmallow)
    test        — Test files
    migration   — Database migration files
    config      — Configuration and settings
    middleware  — Middleware / interceptors
    util        — Utility / helper functions
    worker      — Background job workers / tasks
    generic     — Fallback when no specific role is detected
"""

from __future__ import annotations

import re
from pathlib import Path


# ── Pattern tables ─────────────────────────────────────────────────────────────

# (pattern, file_type) — checked in order; first match wins
_PATH_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Tests
    (re.compile(r"(^|[\\/])(test[s]?|__tests__|spec)[\\/]", re.I), "test"),
    (re.compile(r"\.(test|spec)\.(py|ts|tsx|js|jsx|java|go|rb)$", re.I), "test"),
    # Migrations
    (re.compile(r"(^|[\\/])migrations?[\\/]", re.I), "migration"),
    (re.compile(r"(^|[\\/])alembic[\\/]versions[\\/]", re.I), "migration"),
    # Config
    (re.compile(r"(settings?|config(uration)?|constants?)\.(py|ts|js|go|yaml|yml|toml|env)$", re.I), "config"),
    (re.compile(r"(^|[\\/])config(uration)?[\\/]", re.I), "config"),
    # Workers / tasks
    (re.compile(r"(tasks?|workers?|jobs?|celery)\.(py|ts|js)$", re.I), "worker"),
    (re.compile(r"(^|[\\/])(tasks?|workers?|jobs?)[\\/]", re.I), "worker"),
    # Middleware
    (re.compile(r"middlewar[e]?\.(py|ts|js)$", re.I), "middleware"),
    (re.compile(r"(^|[\\/])middlewar[e]?[\\/]", re.I), "middleware"),
    # Controllers / routes
    (re.compile(r"(controller|router?|routes?|handler|endpoint|view)\.(py|ts|tsx|js|jsx|java|go)$", re.I), "controller"),
    (re.compile(r"(^|[\\/])(controllers?|routes?|handlers?|views?)[\\/]", re.I), "controller"),
    # Repositories / DAOs
    (re.compile(r"(repository|repo|dao|store)\.(py|ts|js|java|go)$", re.I), "repository"),
    (re.compile(r"(^|[\\/])(repositories|repos?|daos?)[\\/]", re.I), "repository"),
    # Schemas
    (re.compile(r"schema[s]?\.(py|ts|js)$", re.I), "schema"),
    (re.compile(r"(^|[\\/])schemas?[\\/]", re.I), "schema"),
    # Models / entities
    (re.compile(r"(model|entity|domain)\.(py|ts|js|java|go)$", re.I), "model"),
    (re.compile(r"(^|[\\/])(models?|entities|domain)[\\/]", re.I), "model"),
    # Services
    (re.compile(r"service[s]?\.(py|ts|js|java|go)$", re.I), "service"),
    (re.compile(r"(^|[\\/])services?[\\/]", re.I), "service"),
    # Utils
    (re.compile(r"(util[s]?|helper[s]?|common|shared)\.(py|ts|js|java|go)$", re.I), "util"),
    (re.compile(r"(^|[\\/])(utils?|helpers?|common|shared)[\\/]", re.I), "util"),
]

# Import-based heuristics: if file imports these, guess its type
_IMPORT_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(fastapi|flask|django\.views|express|@Get\(|@Post\(|@Controller)", re.I), "controller"),
    (re.compile(r"(sqlalchemy|typeorm|django\.db\.models|gorm|hibernate)", re.I), "model"),
    (re.compile(r"(celery|dramatiq|rq|bull|BullMQ)", re.I), "worker"),
    (re.compile(r"(pytest|unittest|@Test|describe\(|it\(|expect\()", re.I), "test"),
    (re.compile(r"(pydantic|zod|joi|marshmallow|yup)", re.I), "schema"),
    (re.compile(r"(fastapi\.middleware|express\.Router|@Middleware)", re.I), "middleware"),
]


def classify_file(file_path: str, source: str = "") -> str:
    """Determine the functional role of a source file.

    Uses a two-pass strategy:
    1. Path/name pattern matching (fast, no source read required).
    2. Import-based heuristics on the source text (only if pass 1 misses).

    Args:
        file_path: Relative path of the file within the repository.
        source: Optional raw source text for import heuristic pass.

    Returns:
        File type string (one of the roles listed in the module docstring).
    """
    normalised = file_path.replace("\\", "/")

    # ── Pass 1: path/name patterns ────────────────────────────────────────────
    for pattern, file_type in _PATH_PATTERNS:
        if pattern.search(normalised):
            return file_type

    # ── Pass 2: import heuristics ─────────────────────────────────────────────
    if source:
        # Only scan the first 60 lines for performance
        header = "\n".join(source.splitlines()[:60])
        for pattern, file_type in _IMPORT_HINTS:
            if pattern.search(header):
                return file_type

    return "generic"


def detect_language(file_path: str) -> str | None:
    """Map a file extension to a canonical language slug.

    Args:
        file_path: File path or filename with extension.

    Returns:
        Language slug string, or None if unrecognised.
    """
    ext = Path(file_path).suffix.lower()
    _EXT_MAP: dict[str, str] = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".scala": "scala",
        ".r": "r",
        ".R": "r",
        ".lua": "lua",
        ".hs": "haskell",
        ".elm": "elm",
        ".ex": "elixir",
        ".exs": "elixir",
        ".erl": "erlang",
        ".hrl": "erlang",
        ".clj": "clojure",
        ".cljs": "clojure",
    }
    return _EXT_MAP.get(ext)


# Files that should always be skipped during parsing
_SKIP_PATTERNS: list[re.Pattern] = [
    re.compile(r"[\\/](node_modules|__pycache__|\.git|\.svn|dist|build|target|out|\.next|\.nuxt|\.venv|venv|env)[\\/]", re.I),
    re.compile(r"\.(min\.js|min\.css|map|lock|sum|mod|pb\.go|pb2\.py|generated\.)"),
    re.compile(r"[\\/]\.", ),  # hidden files / directories
]


def should_skip_file(file_path: str) -> bool:
    """Return True if the file should be excluded from parsing.

    Args:
        file_path: Relative file path within the repository.

    Returns:
        True if the file should be skipped.
    """
    normalised = file_path.replace("\\", "/")
    return any(p.search(normalised) for p in _SKIP_PATTERNS)
