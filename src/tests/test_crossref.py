from vkr import crossref


def _elements():
    return [
        {"type": "figure_caption", "text": "Рисунок {arch} - Architecture"},
        {"type": "table_caption", "text": "Таблица {nfr} - Requirements"},
        {"type": "figure_caption", "text": "Рисунок {er} - ER model"},
        {"type": "listing_caption", "text": "Листинг {api} - Handler"},
        {"type": "math_block", "latex": "v = 1", "number": "{speed}"},
        {"type": "math_block", "latex": "e = 2", "number": "{energy}"},
    ]


def test_build_number_map_sequential_per_kind():
    maps = crossref.build_number_map(_elements())
    assert maps[crossref.FIGURE] == {"arch": "1", "er": "2"}
    assert maps[crossref.TABLE] == {"nfr": "1"}
    assert maps[crossref.LISTING] == {"api": "1"}
    assert maps[crossref.FORMULA] == {"speed": "1", "energy": "2"}


def test_render_caption_label_replaces_key():
    maps = crossref.build_number_map(_elements())
    out = crossref.render_caption_label("Рисунок {er} - ER model", maps, crossref.FIGURE)
    assert out == "Рисунок 2 - ER model"


def test_render_caption_label_unknown_key_kept():
    maps = crossref.build_number_map(_elements())
    out = crossref.render_caption_label("Рисунок {nope} - X", maps, crossref.FIGURE)
    assert out == "Рисунок {nope} - X"


def test_resolve_references_all_kinds():
    maps = crossref.build_number_map(_elements())
    text = "see [рис:er], [табл:nfr], [лист:api] and [форм:energy]"
    out = crossref.resolve_references(text, maps)
    assert out == "see 2, 1, 1 and (2)"


def test_resolve_references_ascii_prefixes():
    maps = crossref.build_number_map(_elements())
    text = "[fig:arch] [tbl:nfr] [lst:api] [eq:speed]"
    out = crossref.resolve_references(text, maps)
    assert out == "1 1 1 (1)"


def test_resolve_references_unknown_kept():
    maps = crossref.build_number_map(_elements())
    assert crossref.resolve_references("[рис:ghost]", maps) == "[рис:ghost]"


def test_resolve_formula_number():
    maps = crossref.build_number_map(_elements())
    assert crossref.resolve_formula_number("{energy}", maps) == "(2)"
    assert crossref.resolve_formula_number("(7)", maps) == "(7)"
    assert crossref.resolve_formula_number(None, maps) is None


def _elements_with_appendices():
    return [
        {"type": "figure_caption", "text": "Рисунок {arch} - Architecture"},
        {"type": "listing_caption", "text": "Листинг {api} - Handler"},
        {"type": "heading", "level": 1, "text": "ПРИЛОЖЕНИЕ А"},
        {"type": "listing_caption", "text": "Листинг {single} - Single line"},
        {"type": "listing_caption", "text": "Листинг {numbering} - Numbering"},
        {"type": "heading", "level": 1, "text": "ПРИЛОЖЕНИЕ Б"},
        {"type": "figure_caption", "text": "Рисунок {cli} - CLI"},
        {"type": "figure_caption", "text": "Рисунок {pkg} - Package"},
    ]


def test_appendix_scoped_numbering():
    maps = crossref.build_number_map(_elements_with_appendices())
    assert maps[crossref.FIGURE]["arch"] == "1"
    assert maps[crossref.LISTING]["api"] == "1"
    assert maps[crossref.LISTING]["single"] == "А.1"
    assert maps[crossref.LISTING]["numbering"] == "А.2"
    assert maps[crossref.FIGURE]["cli"] == "Б.1"
    assert maps[crossref.FIGURE]["pkg"] == "Б.2"


def test_appendix_references_resolve():
    maps = crossref.build_number_map(_elements_with_appendices())
    out = crossref.resolve_references("see [лист:single] and [рис:cli]", maps)
    assert out == "see А.1 and Б.1"


def test_unknown_reference_warns_once():
    import logging

    records = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("vkr")
    handler = _Collect()
    logger.addHandler(handler)
    try:
        crossref.reset_warning_state()
        maps = crossref.build_number_map([])
        crossref.resolve_references("[рис:missing]", maps)
        crossref.resolve_references("[рис:missing]", maps)
    finally:
        logger.removeHandler(handler)

    assert sum("unknown reference" in r.getMessage() for r in records) == 1
