import pytest

from vkr.docx.document import resolve_image_path


@pytest.fixture
def images(tmp_path):
    root = tmp_path / "images"
    (root / "sub").mkdir(parents=True)
    (root / "fig.png").write_bytes(b"x")
    (root / "sub" / "deep.png").write_bytes(b"x")
    return root


@pytest.mark.parametrize(
    "written",
    [
        "fig.png",
        "images/fig.png",
        "../images/fig.png",
        "../../../images/fig.png",
        "./images/fig.png",
        r"images\fig.png",
        "Images/fig.png",
        "assets/fig.png",
        "whatever/fig.png",
    ],
)
def test_every_way_of_writing_the_path_finds_the_file(images, written):
    assert resolve_image_path(written, images) == str(images / "fig.png")


def test_subdirectories_survive(images):
    for written in ("sub/deep.png", "images/sub/deep.png"):
        assert resolve_image_path(written, images) == str(images / "sub" / "deep.png")


def test_the_root_name_is_not_hardcoded(tmp_path):
    for name in ("images", "assets", "pics"):
        root = tmp_path / name
        root.mkdir()
        (root / "fig.png").write_bytes(b"x")
        assert resolve_image_path(f"{name}/fig.png", root) == str(root / "fig.png")


def test_a_missing_file_under_the_named_root_still_points_there(images):
    assert resolve_image_path("images/gone.png", images) == str(images / "gone.png")


def test_an_unresolvable_path_is_left_alone(images):
    assert resolve_image_path("nowhere/gone.png", images) == "nowhere/gone.png"


def test_without_a_root_the_path_is_untouched():
    assert resolve_image_path("images/fig.png", None) == "images/fig.png"
