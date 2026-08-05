import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from vkr import pdf_metadata


def _build_pdf(
    info: bytes = b"", extra_trailer: bytes = b"", catalog: bytes = b""
) -> bytes:
    objects = {
        1: catalog or b"<</Type/Catalog/Pages 2 0 R>>",
        2: b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        3: b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>",
        4: info or b"<</Producer<FEFF0057>/CreationDate(D:20260803022623+03'00')>>",
    }
    out = bytearray(b"%PDF-1.7\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + objects[num] + b"\nendobj\n"

    xref_offset = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for num in sorted(objects):
        out += b"%010d 00000 n \n" % offsets[num]
    out += (
        b"trailer\n<</Size %d/Root 1 0 R/Info 4 0 R"
        b"/ID [<0123456789ABCDEF0123456789ABCDEF>"
        b"<0123456789ABCDEF0123456789ABCDEF>]%s>>\n"
        % (len(objects) + 1, extra_trailer)
    )
    out += b"startxref\n%d\n%%%%EOF\n" % xref_offset
    return bytes(out)


def _last_object_dict(data: bytes, num: int) -> bytes:
    return pdf_metadata._plain_object_dict(pdf_metadata._object_dicts(data), num)


def _hex_string(value: str) -> bytes:
    return b"<" + ("﻿" + value).encode("utf-16-be").hex().upper().encode() + b">"


def _text_value(dictionary: bytes, key: str) -> str | None:
    m = re.search(rb"/" + key.encode() + rb"\s*<([0-9A-Fa-f]+)>", dictionary)
    if m is None:
        return None
    decoded = bytes.fromhex(m.group(1).decode()).decode("utf-16-be")
    return decoded.lstrip("﻿")


def _xmp(data: bytes) -> str:
    packets = re.findall(rb"<\?xpacket begin.*?<\?xpacket end.*?\?>", data, re.DOTALL)
    return packets[-1].decode("utf-8")


def _info(data: bytes) -> bytes:
    xref = pdf_metadata._read_xref(data)
    return _last_object_dict(data, xref.info_num)


NEUTRAL = pdf_metadata.NEUTRAL_TIMESTAMP.strftime("%Y%m%d%H%M%S").encode()

SAMPLE = {
    "title": "Разработка системы",
    "author": "Иванов И. И.",
    "subject": "ВКР",
    "keywords": "markdown, ГОСТ",
    "language": "ru-RU",
    "created": "2026-01-15",
    "modified": "2026-06-23 18:45:00",
}


def test_neutralise_keeps_every_offset_valid():
    data = _build_pdf(extra_trailer=b"/DocChecksum /24D9BDFF2EC211D3CA73D139E7CCF41F")
    out = pdf_metadata._neutralise_converter_values(data)

    assert len(out) == len(data)
    assert b"D:20260803022623" not in out
    assert b"D:" + NEUTRAL + b"+00'00'" in out
    assert b"0123456789ABCDEF" not in out
    assert b"/DocChecksum /00000000000000000000000000000000" in out


def test_neutralise_handles_a_short_date():
    data = _build_pdf(info=b"<</CreationDate(D:20260803)>>")
    out = pdf_metadata._neutralise_converter_values(data)

    assert len(out) == len(data)
    assert b"(D:" + NEUTRAL[:8] + b")" in out


def test_configured_fields_reach_the_info_dictionary(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)

    info = _info(pdf.read_bytes())
    assert _text_value(info, "Title") == "Разработка системы"
    assert _text_value(info, "Author") == "Иванов И. И."
    assert _text_value(info, "Subject") == "ВКР"
    assert _text_value(info, "Keywords") == "markdown, ГОСТ"
    assert b"/CreationDate(D:20260115000000+00'00')" in info
    assert b"/ModDate(D:20260623184500+00'00')" in info


def test_fields_without_a_pdf_equivalent_are_dropped(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    metadata = dict(SAMPLE, category="C", comments="COM", last_modified_by="LMB")
    assert pdf_metadata.apply_pdf_metadata(pdf, metadata)

    data = pdf.read_bytes()
    assert b"C" not in _info(data) or _text_value(_info(data), "Title")
    for absent in ("COM", "LMB"):
        assert absent.encode("utf-16-be").hex().upper().encode() not in data


def test_configured_fields_reach_the_xmp_packet(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)

    packet = _xmp(pdf.read_bytes())
    assert "<rdf:li xml:lang=\"x-default\">Разработка системы</rdf:li>" in packet
    assert "<rdf:li>Иванов И. И.</rdf:li>" in packet
    assert "<pdf:Keywords>markdown, ГОСТ</pdf:Keywords>" in packet
    assert "<rdf:li>ru-RU</rdf:li>" in packet
    assert "<xmp:CreateDate>2026-01-15T00:00:00Z</xmp:CreateDate>" in packet
    assert "<xmp:ModifyDate>2026-06-23T18:45:00Z</xmp:ModifyDate>" in packet


def test_nothing_names_the_software_that_made_the_file(tmp_path):
    pdf = tmp_path / "out.pdf"
    producer = _hex_string("LibreOffice 25.8.1.1 (X86_64) / LibreOffice Community")
    pdf.write_bytes(
        _build_pdf(
            info=b"<</Producer" + producer + b"/Creator(Writer)"
            b"/CreationDate(D:20260803022623+03'00')>>"
        )
    )
    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)

    data = pdf.read_bytes()
    info = _info(data)
    assert _text_value(info, "Producer") is None
    assert _text_value(info, "Creator") is None
    assert b"/Producer" not in info and b"/Creator" not in info
    assert "<pdf:Producer>" not in _xmp(data)
    assert "<xmp:CreatorTool>" not in _xmp(data)
    for name in (b"LibreOffice", b"Writer", b"vkr-builder", b"Microsoft"):
        assert name not in data
        assert name.decode().encode("utf-16-be").hex().upper().encode() not in data


def test_a_superseded_xmp_packet_stops_naming_the_converter(tmp_path):
    pdf = tmp_path / "out.pdf"
    packet = (
        b"<?xpacket begin=''?><x:xmpmeta><rdf:RDF><rdf:Description>"
        b"<pdf:Producer>LibreOffice 25.8.1.1 (X86_64)</pdf:Producer>"
        b"<xmp:CreatorTool>Writer</xmp:CreatorTool>"
        b"</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end='w'?>"
    )
    original = _build_pdf()
    pdf.write_bytes(original + b"\n% " + packet + b"\n")

    scrubbed = pdf_metadata._neutralise_converter_values(pdf.read_bytes())
    assert len(scrubbed) == len(original) + len(packet) + 4
    assert b"LibreOffice 25.8.1.1" not in scrubbed
    assert b"<pdf:Producer>" in scrubbed


def test_xmp_escapes_markup(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, {"title": "A & B <C>"})

    packet = _xmp(pdf.read_bytes())
    assert "A &amp; B &lt;C&gt;" in packet


def test_catalog_gets_language_metadata_and_display_title(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)

    data = pdf.read_bytes()
    catalog = _last_object_dict(data, 1)
    assert b"/Lang(ru-RU)" in catalog
    assert b"/ViewerPreferences<</DisplayDocTitle true>>" in catalog
    meta_num = pdf_metadata._dict_ref(catalog, "Metadata")
    assert meta_num is not None
    assert b"/Type/Metadata" in _last_object_dict(data, meta_num)


def test_existing_language_is_replaced_not_duplicated(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf(catalog=b"<</Type/Catalog/Lang(en-US)/Pages 2 0 R>>"))
    assert pdf_metadata.apply_pdf_metadata(pdf, {"language": "ru-RU"})

    catalog = _last_object_dict(pdf.read_bytes(), 1)
    assert b"/Lang(ru-RU)" in catalog
    assert b"en-US" not in catalog


def test_empty_metadata_clears_everything(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, {})

    info = _info(pdf.read_bytes())
    assert _text_value(info, "Title") is None
    assert _text_value(info, "Author") is None
    assert b"/CreationDate(D:" + NEUTRAL + b"+00'00')" in info
    assert b"/ModDate(D:" + NEUTRAL + b"+00'00')" in info


def test_unparsable_date_falls_back_to_the_neutral_one(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, {"created": "yesterday"})

    assert b"/CreationDate(D:" + NEUTRAL + b"+00'00')" in _info(pdf.read_bytes())


def test_same_input_and_metadata_give_the_same_bytes(tmp_path):
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    for path in (first, second):
        path.write_bytes(_build_pdf())
        assert pdf_metadata.apply_pdf_metadata(path, SAMPLE)

    assert first.read_bytes() == second.read_bytes()


def test_different_metadata_gives_a_different_file_id(tmp_path):
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    first.write_bytes(_build_pdf())
    second.write_bytes(_build_pdf())
    pdf_metadata.apply_pdf_metadata(first, SAMPLE)
    pdf_metadata.apply_pdf_metadata(second, dict(SAMPLE, title="Другое"))

    ids = [
        re.findall(rb"/ID \[<([0-9A-F]+)>", path.read_bytes())[-1]
        for path in (first, second)
    ]
    assert ids[0] != ids[1]


def test_update_points_back_at_the_previous_cross_reference(tmp_path):
    pdf = tmp_path / "out.pdf"
    original = _build_pdf()
    pdf.write_bytes(original)
    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)

    data = pdf.read_bytes()
    assert len(data) > len(original)
    assert data[:len(original)] == pdf_metadata._neutralise_converter_values(original)
    prev = int(re.findall(rb"/Prev (\d+)", data)[-1])
    assert data[prev:prev + 4] == b"xref"


def test_not_a_pdf_is_left_alone(tmp_path):
    path = tmp_path / "out.pdf"
    path.write_bytes(b"this is not a PDF")
    assert pdf_metadata.apply_pdf_metadata(path, SAMPLE) is False
    assert path.read_bytes() == b"this is not a PDF"


def test_unreadable_cross_reference_is_left_alone(tmp_path):
    path = tmp_path / "out.pdf"
    broken = _build_pdf().replace(b"startxref", b"startxrefX")
    path.write_bytes(broken)
    assert pdf_metadata.apply_pdf_metadata(path, SAMPLE) is False
    assert path.read_bytes() == broken


def test_missing_file_is_reported_not_raised(tmp_path):
    assert pdf_metadata.apply_pdf_metadata(tmp_path / "nope.pdf", SAMPLE) is False


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits behave differently"
)
def test_a_read_only_pdf_is_replaced_and_keeps_its_mode(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    pdf.chmod(0o444)

    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)
    assert stat.S_IMODE(pdf.stat().st_mode) == 0o444
    assert _text_value(_info(pdf.read_bytes()), "Title") == "Разработка системы"


def test_no_temporary_file_is_left_behind(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)

    assert [p.name for p in tmp_path.iterdir()] == ["out.pdf"]


def test_dict_scanner_steps_over_a_trailing_hex_string():
    body = pdf_metadata._balanced_dict(b"<</Title<FEFF0041>>>tail", 0)
    assert body == b"<</Title<FEFF0041>>>"


def test_dict_scanner_steps_over_nested_parentheses():
    body = pdf_metadata._balanced_dict(rb"<</T(a \) b (c) >>)>>tail", 0)
    assert body == rb"<</T(a \) b (c) >>)>>"


def test_export_pdf_applies_the_metadata(tmp_path, monkeypatch):
    from docx import Document

    from vkr import pdf_export

    src = tmp_path / "in.docx"
    Document().save(str(src))

    def fake_convert(docx_path, pdf_path, libreoffice_path):
        Path(pdf_path).write_bytes(_build_pdf())

    monkeypatch.setattr(pdf_export, "_export_pdf_libreoffice", fake_convert)
    out = pdf_export.export_pdf(src, engine="libreoffice", metadata=SAMPLE)

    assert _text_value(_info(out.read_bytes()), "Title") == "Разработка системы"


def _qpdf() -> str | None:
    return shutil.which("qpdf")


@pytest.mark.skipif(not _qpdf(), reason="qpdf is needed to validate the result")
def test_result_passes_qpdf_check(tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(_build_pdf())
    assert pdf_metadata.apply_pdf_metadata(pdf, SAMPLE)

    done = subprocess.run([_qpdf(), "--check", str(pdf)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.skipif(not _qpdf(), reason="qpdf is needed to build the fixture")
def test_compressed_cross_reference_and_catalog(tmp_path):
    plain = tmp_path / "plain.pdf"
    plain.write_bytes(_build_pdf())
    packed = tmp_path / "packed.pdf"
    subprocess.run(
        [_qpdf(), "--object-streams=generate", str(plain), str(packed)], check=True
    )
    assert b"/ObjStm" in packed.read_bytes()

    assert pdf_metadata.apply_pdf_metadata(packed, SAMPLE)

    done = subprocess.run(
        [_qpdf(), "--check", str(packed)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr
    shown = subprocess.run(
        [_qpdf(), "--show-object=trailer", str(packed)], capture_output=True, text=True
    )
    assert "/XRef" in shown.stdout

    root = pdf_metadata._read_xref(packed.read_bytes()).root_num
    catalog = subprocess.run(
        [_qpdf(), f"--show-object={root}", str(packed)], capture_output=True, text=True
    )
    assert "ru-RU" in catalog.stdout
    assert "/Metadata" in catalog.stdout


def test_a_converter_that_dates_its_own_xmp_is_neutralised(tmp_path):
    packet = (
        b"<?xpacket begin='' id='W5M0'?>"
        b"<xmp:CreateDate>2026-08-03T05:09:19+03:00</xmp:CreateDate>"
        b"<xmp:ModifyDate>2026-08-03T05:09:29+03:00</xmp:ModifyDate>"
        b"<xmp:MetadataDate>2026-08-03T05:09:29+03:00</xmp:MetadataDate>"
        b"<dc:date><rdf:Seq><rdf:li>2026-08-03T05:09:19+03:00</rdf:li></rdf:Seq></dc:date>"
        b"<?xpacket end='w'?>"
    )
    original = _build_pdf()
    scrubbed = pdf_metadata._neutralise_converter_values(original + b"\n% " + packet)

    assert len(scrubbed) == len(original) + len(packet) + 3
    assert b"2026-08-03T05:09" not in scrubbed
    assert b"+03:00" not in scrubbed
    assert scrubbed.count(b"2026-01-01T00:00:00+00:00") == 4


def test_a_date_written_as_an_attribute_is_neutralised_too():
    packet = (
        b"<?xpacket begin='' id='W5M0'?>"
        b"<rdf:Description xmp:CreateDate=\"2026-08-03T05:09:19+03:00\""
        b" xmp:ModifyDate=\"2026-08-03T05:09:29+03:00\"/>"
        b"<?xpacket end='w'?>"
    )
    original = _build_pdf()
    scrubbed = pdf_metadata._neutralise_converter_values(original + b"\n% " + packet)

    assert len(scrubbed) == len(original) + len(packet) + 3
    assert b"2026-08-03T05:09" not in scrubbed
    assert scrubbed.count(b"2026-01-01T00:00:00+00:00") == 2


def test_a_date_the_author_wrote_into_a_text_field_is_left_alone():
    packet = (
        b"<?xpacket begin='' id='W5M0'?>"
        b"<xmp:CreateDate>2026-08-03T05:09:19+03:00</xmp:CreateDate>"
        b"<dc:description><rdf:Alt><rdf:li>measured at 2026-08-03T05:09:19+03:00"
        b"</rdf:li></rdf:Alt></dc:description>"
        b"<?xpacket end='w'?>"
    )
    original = _build_pdf()
    scrubbed = pdf_metadata._neutralise_converter_values(original + b"\n% " + packet)

    assert b"<xmp:CreateDate>2026-01-01T00:00:00+00:00</" in scrubbed
    assert scrubbed.count(b"2026-08-03T05:09:19+03:00") == 1


def test_a_converter_that_mints_a_fresh_uuid_is_neutralised():
    def packet(uuid: bytes) -> bytes:
        return (
            b"<?xpacket begin='' id='W5M0'?>"
            b"<xmpMM:DocumentID>uuid:" + uuid + b"</xmpMM:DocumentID>"
            b"<xmpMM:InstanceID>uuid:" + uuid + b"</xmpMM:InstanceID>"
            b"<?xpacket end='w'?>"
        )

    original = _build_pdf()
    first = pdf_metadata._neutralise_converter_values(
        original + b"\n% " + packet(b"318F3C84-6C5B-4881-B74E-468C95CDE03A")
    )
    second = pdf_metadata._neutralise_converter_values(
        original + b"\n% " + packet(b"24B06E33-D4E8-43A2-9136-F98789C8D35C")
    )

    assert first == second
    assert first.count(b"uuid:00000000-0000-0000-0000-000000000000") == 2
    assert pdf_metadata._document_id(first, {}) == pdf_metadata._document_id(second, {})


def test_the_converters_timezone_is_not_left_in_a_pdf_date():
    data = _build_pdf(info=b"<</CreationDate(D:20260803050919+03'00')>>")
    out = pdf_metadata._neutralise_converter_values(data)

    assert len(out) == len(data)
    assert b"+03'00'" not in out
    assert b"+00'00'" in out


def test_an_indirect_length_is_not_read_as_a_number():
    assert pdf_metadata._dict_int(b"<</Length 12 0 R/Filter/FlateDecode>>", "Length") is None
    assert pdf_metadata._dict_int(b"<</Length 42/Filter/FlateDecode>>", "Length") == 42
