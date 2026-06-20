"""Tree-sitter based code chunker — splits files into function/class level chunks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    file_path: str
    symbol_name: str
    symbol_type: str  # "function" | "class" | "module"
    language: str
    start_line: int
    end_line: int
    content: str
    metadata: dict = field(default_factory=dict)


def _iter_lines_slice(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start:end])


def _chunk_python_fallback(file_path: str, source: str) -> list[CodeChunk]:
    """Fallback chunker using simple heuristics (no tree-sitter) for Python."""
    chunks: list[CodeChunk] = []
    lines = source.splitlines(keepends=True)
    current_block: list[str] = []
    current_name = "module_top"
    current_type = "module"
    current_start = 0

    def flush(end_line: int) -> None:
        content = "".join(current_block).strip()
        if content:
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    symbol_name=current_name,
                    symbol_type=current_type,
                    language="python",
                    start_line=current_start,
                    end_line=end_line,
                    content=content,
                )
            )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            flush(i)
            name_part = stripped.split("(")[0].replace("def ", "").replace("async ", "").strip()
            current_name = name_part
            current_type = "function"
            current_start = i
            current_block = [line]
        elif stripped.startswith("class "):
            flush(i)
            name_part = stripped.split("(")[0].split(":")[0].replace("class ", "").strip()
            current_name = name_part
            current_type = "class"
            current_start = i
            current_block = [line]
        else:
            current_block.append(line)

    flush(len(lines))
    return chunks


def chunk_file(file_path: str) -> list[CodeChunk]:
    """Chunk a source file into function/class level chunks.

    Uses tree-sitter if available, falls back to heuristic chunking.

    Args:
        file_path: Absolute path to the source file.

    Returns:
        List of CodeChunk objects.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning("File not found for chunking: %s", file_path)
        return []

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Could not read %s: %s", file_path, exc)
        return []

    ext = path.suffix.lower()

    # Try tree-sitter for Python
    if ext == ".py":
        try:
            return _chunk_with_tree_sitter_python(file_path, source)
        except Exception as exc:
            logger.debug("tree-sitter chunking failed for %s (%s), using fallback.", file_path, exc)
            return _chunk_python_fallback(file_path, source)

    # Generic fallback: treat whole file as a single chunk
    lines = source.splitlines()
    return [
        CodeChunk(
            file_path=file_path,
            symbol_name=path.name,
            symbol_type="module",
            language=ext.lstrip(".") or "unknown",
            start_line=0,
            end_line=len(lines),
            content=source[:8000],  # cap at 8KB
        )
    ]


def _chunk_with_tree_sitter_python(file_path: str, source: str) -> list[CodeChunk]:
    """Use tree-sitter to chunk Python code into function/class nodes."""
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    PY_LANGUAGE = Language(tspython.language())
    parser = Parser(PY_LANGUAGE)

    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    lines = source.splitlines(keepends=True)
    chunks: list[CodeChunk] = []

    def visit(node) -> None:
        if node.type in ("function_definition", "class_definition"):
            start = node.start_point[0]
            end = node.end_point[0] + 1
            # Extract name
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else "unknown"
            sym_type = "function" if node.type == "function_definition" else "class"
            content = _iter_lines_slice(lines, start, end)
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    symbol_name=name,
                    symbol_type=sym_type,
                    language="python",
                    start_line=start,
                    end_line=end,
                    content=content,
                )
            )
            # Don't recurse into nested functions/classes to avoid duplication
            return
        for child in node.children:
            visit(child)

    visit(root)
    return chunks
