from vkr.docx.bookmarks import heading_bookmark_name


def test_heading_bookmark_name_matches_build_slug():
    assert heading_bookmark_name("1 Первая глава") == "_1_Первая_глава"
    assert heading_bookmark_name("  2 Вторая глава  ") == "_2_Вторая_глава"


def test_heading_bookmark_name_truncates_long_titles():
    long_title = "1 " + "А" * 80
    assert len(heading_bookmark_name(long_title)) == 40
