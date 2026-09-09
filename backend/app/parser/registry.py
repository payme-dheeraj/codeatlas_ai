"""Language parser registry.

Maps language slugs to their concrete BaseLanguageParser subclasses.
Parsers are instantiated lazily — import errors for missing grammar
packages are surfaced at parse time, not at startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.parser.base import BaseLanguageParser

logger = get_logger(__name__)

# Lazy registry: language slug → parser class (imported on first use)
_REGISTRY: dict[str, type["BaseLanguageParser"]] = {}
_REGISTERED = False


def _register_all() -> None:
    """Populate the registry with all available language parsers.

    Import errors are caught individually so a missing grammar package
    for one language does not prevent others from working.
    """
    global _REGISTERED
    if _REGISTERED:
        return

    candidates: list[tuple[str, str, str]] = [
        ("python", "app.parser.languages.python", "PythonParser"),
        ("typescript", "app.parser.languages.typescript", "TypeScriptParser"),
        ("javascript", "app.parser.languages.javascript", "JavaScriptParser"),
        ("java", "app.parser.languages.java", "JavaParser"),
        ("go", "app.parser.languages.go", "GoParser"),
        ("rust", "app.parser.languages.rust", "RustParser"),
    ]

    for lang, module_path, class_name in candidates:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            _REGISTRY[lang] = cls
            logger.debug("parser_registered", language=lang)
        except Exception as exc:
            logger.warning(
                "parser_unavailable",
                language=lang,
                error=str(exc),
            )

    _REGISTERED = True


def get_parser(language: str) -> "BaseLanguageParser | None":
    """Return a parser instance for the given language slug, or None.

    Args:
        language: Language slug (e.g. ``"python"``, ``"typescript"``).

    Returns:
        An instantiated BaseLanguageParser, or None if unsupported.
    """
    _register_all()
    cls = _REGISTRY.get(language)
    if cls is None:
        return None
    return cls()


def supported_languages() -> list[str]:
    """Return sorted list of language slugs with available parsers.

    Returns:
        List of supported language slug strings.
    """
    _register_all()
    return sorted(_REGISTRY.keys())
