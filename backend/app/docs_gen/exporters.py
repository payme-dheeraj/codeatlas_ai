"""Document exporters — convert Markdown to HTML, Confluence XML, and Notion blocks.

All exporters take a Markdown string and return the target format string or
structure. They are intentionally dependency-light; heavy parsing uses the
``markdown`` and ``lxml`` packages which are already in the dependency tree.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any


# ── HTML exporter ─────────────────────────────────────────────────────────────


def to_html(markdown_content: str, title: str = "Documentation") -> str:
    """Convert Markdown to a standalone HTML document.

    Uses the ``markdown`` package with fenced code block and table extensions.
    Falls back to a basic regex-based conversion if the package is unavailable.

    Args:
        markdown_content: Source Markdown string.
        title: Page title for the ``<title>`` tag.

    Returns:
        Full HTML document string.
    """
    try:
        import markdown as md_lib
        body_html = md_lib.markdown(
            markdown_content,
            extensions=["fenced_code", "tables", "toc", "attr_list"],
        )
    except ImportError:
        body_html = _basic_md_to_html(markdown_content)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_escape_html(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.6;
            color: #24292e; }}
    h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: .3em; }}
    pre {{ background: #f6f8fa; border-radius: 6px; padding: 16px; overflow-x: auto; }}
    code {{ background: #f6f8fa; border-radius: 3px; padding: .2em .4em; font-size: 85%; }}
    pre code {{ background: none; padding: 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #dfe2e5; padding: 6px 13px; }}
    tr:nth-child(even) {{ background: #f6f8fa; }}
    blockquote {{ border-left: 4px solid #dfe2e5; margin: 0; padding: 0 1em; color: #6a737d; }}
  </style>
</head>
<body>
{body_html}
</body>
</html>"""


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _basic_md_to_html(md: str) -> str:
    """Minimal Markdown → HTML conversion for environments without the markdown package.

    Args:
        md: Markdown string.

    Returns:
        HTML fragment string.
    """
    html = md
    # Headings
    for level in range(6, 0, -1):
        html = re.sub(
            rf"^{'#' * level} (.+)$",
            rf"<h{level}>\1</h{level}>",
            html,
            flags=re.MULTILINE,
        )
    # Bold/italic
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    # Code blocks
    html = re.sub(r"```[a-z]*\n(.*?)```", r"<pre><code>\1</code></pre>", html, flags=re.DOTALL)
    # Inline code
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    # Paragraphs
    paragraphs = re.split(r"\n{2,}", html)
    html = "\n".join(f"<p>{p.strip()}</p>" if not p.strip().startswith("<") else p for p in paragraphs)
    return html


# ── Confluence XML exporter ───────────────────────────────────────────────────


def to_confluence_xml(markdown_content: str, title: str = "Page") -> str:
    """Convert Markdown to Confluence Storage Format XML.

    Produces valid Confluence page body XML that can be uploaded via the
    Confluence REST API (``body.storage.value`` field).

    Args:
        markdown_content: Source Markdown string.
        title: Page title (used as the root page macro header).

    Returns:
        Confluence Storage Format XML string.
    """
    lines = markdown_content.splitlines()
    parts: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Headings
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            text = _escape_html(m.group(2))
            parts.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Fenced code block
        if line.startswith("```"):
            lang = line[3:].strip() or "text"
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code = "\n".join(code_lines)
            parts.append(
                f'<ac:structured-macro ac:name="code">'
                f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
                f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>'
                f"</ac:structured-macro>"
            )
            i += 1
            continue

        # Bullet list
        if line.startswith("- ") or line.startswith("* "):
            items: list[str] = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("* ")):
                items.append(f"<li>{_inline_confluence(lines[i][2:])}</li>")
                i += 1
            parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Table (simple)
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[-| :]+\|$", lines[i + 1]):
            table_lines: list[str] = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            parts.append(_md_table_to_confluence(table_lines))
            continue

        # Blockquote
        if line.startswith("> "):
            parts.append(f"<blockquote><p>{_inline_confluence(line[2:])}</p></blockquote>")
            i += 1
            continue

        # Normal paragraph
        stripped = line.strip()
        if stripped:
            parts.append(f"<p>{_inline_confluence(stripped)}</p>")
        i += 1

    return "\n".join(parts)


def _inline_confluence(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    return text


def _md_table_to_confluence(rows: list[str]) -> str:
    cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
    if not cells:
        return ""
    header = cells[0]
    data = [r for r in cells[2:] if r]  # skip separator row
    lines = ["<table><tbody>"]
    lines.append("<tr>" + "".join(f"<th>{_escape_html(c)}</th>" for c in header) + "</tr>")
    for row in data:
        lines.append("<tr>" + "".join(f"<td>{_escape_html(c)}</td>" for c in row) + "</tr>")
    lines.append("</tbody></table>")
    return "\n".join(lines)


# ── Notion blocks exporter ────────────────────────────────────────────────────


def to_notion_blocks(markdown_content: str) -> list[dict[str, Any]]:
    """Convert Markdown to a list of Notion block API objects.

    Produces a structure compatible with the Notion API
    ``blocks.children.append`` endpoint.

    Args:
        markdown_content: Source Markdown string.

    Returns:
        List of Notion block dicts.
    """
    blocks: list[dict] = []
    lines = markdown_content.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # Heading
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            level = min(len(m.group(1)), 3)
            heading_type = f"heading_{level}"
            blocks.append({
                "type": heading_type,
                heading_type: {
                    "rich_text": [{"type": "text", "text": {"content": m.group(2)}}]
                },
            })
            i += 1
            continue

        # Fenced code block
        if line.startswith("```"):
            lang = line[3:].strip() or "plain text"
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                    "language": lang,
                },
            })
            i += 1
            continue

        # Bullet
        if line.startswith("- ") or line.startswith("* "):
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                },
            })
            i += 1
            continue

        # Divider
        if re.match(r"^---+$", line.strip()):
            blocks.append({"type": "divider", "divider": {}})
            i += 1
            continue

        # Paragraph
        stripped = line.strip()
        if stripped:
            blocks.append({
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": stripped}}]
                },
            })
        i += 1

    return blocks
