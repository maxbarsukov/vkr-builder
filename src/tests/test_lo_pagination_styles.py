from vkr import docx_style


def test_lo_skip_styles_follow_word_styles():
    docx_style.configure_style_names({"body": "My Body Style"})
    try:
        names = docx_style.lo_pagination_skip_paragraph_styles()
        assert "My Body Style" in names
        assert "ДИПЛОМ - Обычный текст" not in names
    finally:
        docx_style.reset_style_names_to_defaults()
