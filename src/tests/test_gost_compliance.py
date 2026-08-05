from vkr import gost_compliance


def test_caption_separator_accepts_spaced_hyphen():
    assert (
        gost_compliance.caption_separator_issue("Рисунок {a} - Caption")
        is None
    )


def test_caption_separator_rejects_tight_dash():
    assert gost_compliance.caption_separator_issue("Таблица 1-Caption") is not None


def test_numbering_gap_detected():
    elements = [
        {"type": "table_caption", "text": "Таблица 1 - A"},
        {"type": "table", "header": ["a"], "rows": [["1"]]},
        {"type": "table_caption", "text": "Таблица 3 - B"},
        {"type": "table", "header": ["a"], "rows": [["2"]]},
    ]
    issues = gost_compliance.numbering_gap_issues(elements)
    assert any("gap" in msg for _, msg in issues)


def test_structural_heading_unknown():
    elements = [{"type": "heading", "level": 1, "text": "Random Section"}]
    issues = gost_compliance.structural_heading_issues(elements)
    assert len(issues) == 1
