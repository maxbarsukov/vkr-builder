from __future__ import annotations

import zipfile
from unittest.mock import patch

from tests.conftest import requires_word

from vkr import docx_build
from vkr import docx_style


def _sect_pr_attrs(document_xml: str) -> dict[str, str]:
    idx = document_xml.find("<w:sectPr")
    if idx < 0:
        return {}
    chunk = document_xml[idx : idx + 800]
    attrs: dict[str, str] = {}
    for tag in ("pgSz", "pgMar", "pgNumType"):
        marker = f"w:{tag} "
        pos = chunk.find(marker)
        if pos < 0:
            continue
        end = chunk.find("/>", pos)
        fragment = chunk[pos:end]
        for part in fragment.split():
            if part.startswith("w:") and "=" in part:
                key, _, val = part.partition("=")
                attrs[f"{tag}.{key[2:]}"] = val.strip('"')
    return attrs


@requires_word
def test_build_applies_custom_typography_and_styles(tmp_path):
    md_path = tmp_path / "one.md"
    md_path.write_text("Body paragraph with text.\n", encoding="utf-8")
    out = tmp_path / "out.docx"

    typography = {
        "font_family": "Arial",
        "body_font_pt": 12.0,
        "page_number_from": 9,
        "margin_left_cm": 2.5,
        "margin_right_cm": 2.0,
        "margin_top_cm": 2.5,
        "margin_bottom_cm": 2.0,
    }
    styles = {"body": "Custom Body Style"}

    with patch("vkr.docx_build.detect_heading_pages", return_value=[]):
        docx_build.build(
            str(md_path),
            str(out),
            typography=typography,
            styles=styles,
            pagination_engine="word",
        )

    with zipfile.ZipFile(out) as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8")
        styles_xml = zf.read("word/styles.xml").decode("utf-8")
    attrs = _sect_pr_attrs(document_xml)

    assert attrs.get("pgMar.left") == "1417"
    assert attrs.get("pgNumType.start") == "9"
    assert "Custom Body Style" in styles_xml
    assert "Arial" in styles_xml or "Arial" in document_xml

    docx_style.reset_typography_to_defaults()
    docx_style.reset_style_names_to_defaults()
