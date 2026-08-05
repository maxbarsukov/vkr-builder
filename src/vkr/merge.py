from __future__ import annotations

from pathlib import Path


def merge_markdown_files(
    content_root: Path,
    relative_paths: list[str] | tuple[str, ...],
    output_path: Path,
    *,
    separator: str = "\n\n",
) -> Path:
    content_root = content_root.resolve()
    output_path = output_path.resolve()
    parts: list[str] = []
    for rel in relative_paths:
        p = (content_root / rel).resolve()
        if not p.is_relative_to(content_root):
            raise ValueError(
                f"Markdown path escapes markdown_dir: {rel!r} -> {p}"
            )
        if not p.is_file():
            raise FileNotFoundError(f"Markdown file to merge not found: {p}")
        text = p.read_text(encoding="utf-8").rstrip()
        parts.append(f"<!-- file: {rel} -->\n\n{text}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body = separator.join(parts)
    if body and not body.endswith("\n"):
        body += "\n"
    output_path.write_text(body, encoding="utf-8")
    return output_path
