from __future__ import annotations

import zipfile

from vkr import docx_build
from vkr import docx_style


def _pgnum_start(document_xml: str) -> str | None:
    marker = 'w:pgNumType w:start="'
    idx = document_xml.find(marker)
    if idx < 0:
        return None
    start = idx + len(marker)
    end = document_xml.find('"', start)
    return document_xml[start:end]


def test_pgnum_type_from_typography(tmp_path):
    out = tmp_path / "page.docx"
    elements = [{"type": "para", "text": "Body text."}]
    docx_style.apply_typography_from_mapping({"page_number_from": 12})
    try:
        docx_build._build_pass(str(out), elements, None, assets_root=None)
        with zipfile.ZipFile(out) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert _pgnum_start(xml) == "12"
    finally:
        docx_style.reset_typography_to_defaults()


def test_pgnum_type_default_matches_config(tmp_path):
    from vkr import config

    out = tmp_path / "page.docx"
    elements = [{"type": "para", "text": "Default numbering."}]
    expected = str(config.default_page_number_from())
    docx_style.reset_typography_to_defaults()
    try:
        docx_build._build_pass(str(out), elements, None, assets_root=None)
        with zipfile.ZipFile(out) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert _pgnum_start(xml) == expected
    finally:
        docx_style.reset_typography_to_defaults()
