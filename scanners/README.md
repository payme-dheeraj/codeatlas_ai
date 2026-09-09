# Scanners Directory

In CodeAtlas AI, the repository scanner and multi-language parsers are organized within the backend application package:

- **Repository Scanner & File Traversal**: [`backend/app/scanner/scanner.py`](../backend/app/scanner/scanner.py)
- **Language Parser Registry**: [`backend/app/parser/registry.py`](../backend/app/parser/registry.py)
- **Base Tree-sitter Parser**: [`backend/app/parser/base.py`](../backend/app/parser/base.py)
- **Language-specific Parsers**:
  - Python: [`backend/app/parser/languages/python.py`](../backend/app/parser/languages/python.py)
  - TypeScript / JavaScript: [`backend/app/parser/languages/typescript.py`](../backend/app/parser/languages/typescript.py)
  - Go: [`backend/app/parser/languages/go.py`](../backend/app/parser/languages/go.py)
  - Java: [`backend/app/parser/languages/java.py`](../backend/app/parser/languages/java.py)
  - Rust: [`backend/app/parser/languages/rust.py`](../backend/app/parser/languages/rust.py)

This directory is preserved for workspace structure consistency.
