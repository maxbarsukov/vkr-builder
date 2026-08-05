from pathlib import Path

import pytest

from vkr import merge


def test_merge_rejects_path_outside_content_root(tmp_path):
    content_root = tmp_path / "content"
    content_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")

    rel = Path("..") / "outside.md"
    with pytest.raises(ValueError, match="escapes markdown_dir"):
        merge.merge_markdown_files(
            content_root,
            [str(rel).replace("\\", "/")],
            tmp_path / "bundle.md",
        )


def test_merge_reads_file_inside_content_root(tmp_path):
    content_root = tmp_path / "content"
    content_root.mkdir()
    chapter = content_root / "ch.md"
    chapter.write_text("Hello", encoding="utf-8")
    out = tmp_path / "bundle.md"

    merge.merge_markdown_files(content_root, ["ch.md"], out)
    assert "Hello" in out.read_text(encoding="utf-8")
