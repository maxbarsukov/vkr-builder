import shutil

from vkr import docx_build


def test_safe_copy_falls_back_when_locked(tmp_path, monkeypatch):
    src = tmp_path / "built.docx"
    src.write_bytes(b"PK\x03\x04 fake docx")
    dst = tmp_path / "VKR.docx"

    real_copy = shutil.copy
    calls = {"n": 0}

    def fake_copy(s, d):
        calls["n"] += 1
        if str(d) == str(dst):
            raise PermissionError("locked by Word")
        return real_copy(s, d)

    monkeypatch.setattr(docx_build.shutil, "copy", fake_copy)

    result = docx_build._safe_copy_output(str(src), str(dst))
    assert result != str(dst)
    assert result.name == "VKR-new.docx"
    assert result.is_file()


def test_safe_copy_writes_destination_when_free(tmp_path):
    src = tmp_path / "built.docx"
    src.write_bytes(b"PK\x03\x04 fake docx")
    dst = tmp_path / "VKR.docx"

    result = docx_build._safe_copy_output(str(src), str(dst))
    assert str(result) == str(dst)
    assert dst.is_file()
