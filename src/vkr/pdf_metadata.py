from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import shutil
import zlib
from pathlib import Path
from typing import NamedTuple

from .config import NEUTRAL_TIMESTAMP
from .logging_setup import get_logger

log = get_logger("pdf")

_MAX_DICT_BYTES = 1 << 20

_XMP_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "pdf": "http://ns.adobe.com/pdf/1.3/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
}


def apply_pdf_metadata(pdf_path: str | Path, metadata: dict | None) -> bool:
    path = Path(pdf_path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        _warn("could not read the PDF back: %s", exc)
        return False

    patched = _rewrite(data, dict(metadata or {}))
    if patched is None:
        return False

    try:
        _replace_contents(path, patched)
    except OSError as exc:
        _warn("could not write the PDF metadata: %s", exc)
        return False
    log.debug("PDF metadata applied: %s", path)
    return True


def _replace_contents(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".vkr-tmp")
    try:
        tmp.write_bytes(data)
        try:
            shutil.copymode(path, tmp)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _warn(message: str, *args) -> None:
    log.warning(message, *args, extra={"rule": "metadata"})


def _rewrite(data: bytes, metadata: dict) -> bytes | None:
    if not data.startswith(b"%PDF-"):
        _warn("not a PDF file; metadata left as the converter wrote it")
        return None

    parsed = _object_dicts(data)
    data = _neutralise_converter_values(data, parsed)
    parsed = [(num, data[start:after], start, after) for num, _, start, after in parsed]

    xref = _read_xref(data)
    if xref is None:
        _warn("could not read the PDF cross-reference table; metadata skipped")
        return None

    next_num = xref.size
    objects: list[tuple[int, bytes]] = []

    info_num = xref.info_num
    if info_num is None:
        info_num = next_num
        next_num += 1
    objects.append((info_num, _object(info_num, _info_dict(metadata))))

    catalog = _catalog_dict(data, xref.root_num, parsed)
    meta_num = _dict_ref(catalog, "Metadata") if catalog is not None else None
    if meta_num is None:
        meta_num = _find_metadata_stream(parsed)
    if meta_num is None and catalog is not None:
        meta_num = next_num
        next_num += 1

    if meta_num is not None:
        objects.append((meta_num, _xmp_object(meta_num, metadata)))
    else:
        _warn("could not attach the XMP packet; only the PDF info dictionary was set")

    if catalog is not None:
        patched = _patch_catalog(catalog, meta_num, metadata)
        if patched != catalog:
            objects.append((xref.root_num, _object(xref.root_num, patched)))

    doc_id = _document_id(data, metadata)
    return _append_update(
        data, objects, xref=xref, info_num=info_num, doc_id=doc_id
    )


def _document_id(data: bytes, metadata: dict) -> bytes:
    digest = hashlib.md5(usedforsecurity=False)
    digest.update(data)
    for key in sorted(metadata):
        digest.update(f"{key}={metadata[key]}\n".encode("utf-8"))
    return digest.hexdigest().upper().encode("ascii")


_DATE_RE = re.compile(
    rb"/(?:CreationDate|ModDate)\s*\(D:(\d{4,14})([+-]\d{2}'\d{2}')?"
)
_ID_RE = re.compile(rb"/ID\s*\[(.*?)\]", re.DOTALL)
_HEX_RE = re.compile(rb"<([0-9A-Fa-f]+)>")
_CHECKSUM_RE = re.compile(rb"/DocChecksum\s*/([0-9A-Fa-f]+)")
_TOOL_KEY_RE = re.compile(rb"/(?:Producer|Creator)\s*")
_XMP_PACKET_RE = re.compile(rb"<\?xpacket begin.*?<\?xpacket end.*?\?>", re.DOTALL)
_XMP_TOOL_RE = re.compile(rb"<(pdf:Producer|xmp:CreatorTool)>([^<]*)</")
_XMP_DATE_RE = re.compile(
    rb"(?:<|\s)(?:xmp:(?:Create|Modify|Metadata)Date|stEvt:when)(?:>|=\")([^<\"]*)"
)
_XMP_DATE_BLOCK_RE = re.compile(rb"<dc:date>.*?</dc:date>", re.DOTALL)
_XMP_TIMESTAMP_RE = re.compile(
    rb"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})?"
)
_XMP_ID_RE = re.compile(
    rb"<(xmpMM:(?:Document|Instance|OriginalDocument|Version)ID)>([^<]*)</"
)
_HEX_BYTES = frozenset(b"0123456789abcdefABCDEF")


def _neutralise_converter_values(
    data: bytes, objects: list[tuple[int, bytes, int, int]] | None = None
) -> bytes:
    out = bytearray(data)
    neutral = NEUTRAL_TIMESTAMP.strftime("%Y%m%d%H%M%S").encode("ascii")
    if objects is None:
        objects = _object_dicts(data)

    trailers = [
        (start, body)
        for _, body, start, _ in objects
        if re.search(rb"/Type\s*/XRef\b", body)
    ]
    for m in re.finditer(rb"\btrailer\b", data):
        span = _dict_span(data, m.end())
        if span is not None:
            body, end = span
            trailers.append((end - len(body), body))

    info_nums = {
        num
        for num in (_dict_ref(body, "Info") for _, body in trailers)
        if num is not None
    }
    for num, body, start, _ in objects:
        if num not in info_nums:
            continue
        for m in _DATE_RE.finditer(body):
            digits = m.group(1)
            out[start + m.start(1):start + m.end(1)] = neutral[:len(digits)]
            if m.group(2):
                out[start + m.start(2):start + m.end(2)] = b"+00'00'"
        _blank_tool_names(out, body, start)

    for start, body in trailers:
        for m in _ID_RE.finditer(body):
            for hexval in _HEX_RE.finditer(m.group(1)):
                at = start + m.start(1) + hexval.start(1)
                out[at:at + len(hexval.group(1))] = b"0" * len(hexval.group(1))
        for m in _CHECKSUM_RE.finditer(body):
            out[start + m.start(1):start + m.end(1)] = b"0" * len(m.group(1))

    neutral_iso = NEUTRAL_TIMESTAMP.strftime("%Y-%m-%dT%H:%M:%S").encode("ascii")
    for packet in _XMP_PACKET_RE.finditer(data):
        text, at = packet.group(0), packet.start()
        for m in _XMP_TOOL_RE.finditer(text):
            out[at + m.start(2):at + m.end(2)] = b" " * len(m.group(2))
        for m in _XMP_DATE_RE.finditer(text):
            _neutralise_timestamps(out, m.group(1), at + m.start(1), neutral_iso)
        for m in _XMP_DATE_BLOCK_RE.finditer(text):
            _neutralise_timestamps(out, m.group(0), at + m.start(), neutral_iso)
        for m in _XMP_ID_RE.finditer(text):
            _zero_identifier(out, m.group(2), at + m.start(2))

    return bytes(out)


def _blank_tool_names(out: bytearray, body: bytes, start: int) -> None:
    for m in _TOOL_KEY_RE.finditer(body):
        i = m.end()
        opener = body[i:i + 1]
        if opener == b"(":
            first, last = i + 1, _skip_literal_string(body, i) - 1
        elif opener == b"<":
            last = body.find(b">", i)
            first = i + 1
            if last < 0:
                continue
        else:
            continue
        out[start + first:start + last] = b" " * (last - first)


def _neutralise_timestamps(
    out: bytearray, text: bytes, at: int, neutral_iso: bytes
) -> None:
    for m in _XMP_TIMESTAMP_RE.finditer(text):
        out[at + m.start(1):at + m.end(1)] = neutral_iso
        if m.group(2):
            out[at + m.start(2):at + m.end(2)] = b"+00:00"


def _zero_identifier(out: bytearray, value: bytes, at: int) -> None:
    after_prefix = value.rfind(b":") + 1
    for i in range(after_prefix, len(value)):
        if value[i] in _HEX_BYTES:
            out[at + i] = 0x30


class _Xref(NamedTuple):
    kind: str
    offset: int
    root_num: int
    info_num: int | None
    size: int


def _read_xref(data: bytes) -> _Xref | None:
    offset = _last_startxref(data)
    if offset is None or not 0 < offset < len(data):
        return None

    tail = data[offset:offset + 64].lstrip()
    if tail.startswith(b"xref"):
        marker = data.find(b"trailer", offset)
        if marker < 0:
            return None
        trailer = _dict_at(data, marker + len(b"trailer"))
        kind = "table"
    else:
        header = re.match(rb"\s*\d+\s+\d+\s+obj", data[offset:offset + 64])
        if header is None:
            return None
        trailer = _dict_at(data, offset + header.end())
        kind = "stream"

    if trailer is None:
        return None
    root_num = _dict_ref(trailer, "Root")
    size = _dict_int(trailer, "Size")
    if root_num is None or size is None:
        return None
    return _Xref(kind, offset, root_num, _dict_ref(trailer, "Info"), size)


def _last_startxref(data: bytes) -> int | None:
    marker = data.rfind(b"startxref")
    if marker < 0:
        return None
    m = re.match(rb"startxref\s+(\d+)", data[marker:marker + 64])
    return int(m.group(1)) if m else None


def _dict_span(data: bytes, pos: int) -> tuple[bytes, int] | None:
    while pos < len(data) and data[pos:pos + 1].isspace():
        pos += 1
    if data[pos:pos + 2] != b"<<":
        return None
    body = _balanced_dict(data, pos)
    if body is None:
        return None
    return body, pos + len(body)


def _dict_at(data: bytes, pos: int) -> bytes | None:
    span = _dict_span(data, pos)
    return span[0] if span is not None else None


def _balanced_dict(data: bytes, start: int) -> bytes | None:
    i = start + 2
    depth = 1
    limit = min(len(data), start + _MAX_DICT_BYTES)
    while i < limit:
        c = data[i:i + 1]
        if c == b"(":
            i = _skip_literal_string(data, i)
        elif c == b"<":
            if data[i:i + 2] == b"<<":
                depth += 1
                i += 2
            else:
                end = data.find(b">", i)
                i = len(data) if end < 0 else end + 1
        elif c == b">":
            if data[i:i + 2] == b">>":
                depth -= 1
                i += 2
                if depth == 0:
                    return data[start:i]
            else:
                i += 1
        else:
            i += 1
    return None


def _skip_literal_string(data: bytes, i: int) -> int:
    i += 1
    depth = 1
    while i < len(data):
        c = data[i:i + 1]
        if c == b"\\":
            i += 2
            continue
        if c == b"(":
            depth += 1
        elif c == b")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _dict_ref(text: bytes | None, key: str) -> int | None:
    if text is None:
        return None
    m = re.search(rb"/" + key.encode("ascii") + rb"\s+(\d+)\s+\d+\s+R\b", text)
    return int(m.group(1)) if m else None


def _dict_int(text: bytes | None, key: str) -> int | None:
    if text is None:
        return None
    m = re.search(
        rb"/" + key.encode("ascii") + rb"\s+(\d+)\b(?!\s+\d+\s+R\b)", text
    )
    return int(m.group(1)) if m else None


def _plain_object_dict(objects: list[tuple[int, bytes, int, int]], num: int) -> bytes | None:
    found = None
    for candidate, body, _, _ in objects:
        if candidate == num:
            found = body
    return found


def _catalog_dict(
    data: bytes, root_num: int, objects: list[tuple[int, bytes, int, int]]
) -> bytes | None:
    plain = _plain_object_dict(objects, root_num)
    if plain is not None and b"/Catalog" in plain:
        return plain
    compressed = _object_stream_lookup(data, root_num, objects)
    if compressed is not None:
        return compressed
    if plain is not None:
        return plain
    _warn("could not locate the PDF catalog; /Lang was left as the converter set it")
    return None


def _object_dicts(data: bytes) -> list[tuple[int, bytes, int, int]]:
    found = []
    for m in re.finditer(rb"(?<![0-9])(\d+)\s+0\s+obj\b", data):
        span = _dict_span(data, m.end())
        if span is None:
            continue
        body, after = span
        found.append((int(m.group(1)), body, after - len(body), after))
    return found


def _find_metadata_stream(objects: list[tuple[int, bytes, int, int]]) -> int | None:
    found = None
    for num, body, _, _ in objects:
        if re.search(rb"/Type\s*/Metadata\b", body):
            found = num
    return found


def _object_stream_lookup(
    data: bytes, num: int, objects: list[tuple[int, bytes, int, int]]
) -> bytes | None:
    for _, head, _, after in objects:
        if not re.search(rb"/Type\s*/ObjStm\b", head):
            continue
        payload = _stream_payload(data, after, head)
        if payload is None:
            continue
        count = _dict_int(head, "N")
        first = _dict_int(head, "First")
        if count is None or first is None:
            continue
        pairs = payload[:first].split()
        for i in range(0, min(len(pairs) - 1, count * 2), 2):
            try:
                if int(pairs[i]) != num:
                    continue
                offset = first + int(pairs[i + 1])
            except ValueError:
                break
            found = _dict_at(payload, offset)
            if found is not None:
                return found
    return None


def _stream_payload(data: bytes, pos: int, head: bytes) -> bytes | None:
    m = re.compile(rb"\s*stream\r?\n").match(data, pos)
    if m is None:
        return None
    start = m.end()
    length = _dict_int(head, "Length")
    if length is None or start + length > len(data):
        end = data.find(b"endstream", start)
        if end < 0:
            return None
        raw = data[start:end].rstrip(b"\r\n")
    else:
        raw = data[start:start + length]
    if not re.search(rb"/Filter\s*/FlateDecode\b", head):
        return raw
    try:
        return zlib.decompress(raw)
    except zlib.error:
        return None


def _object(num: int, body: bytes) -> bytes:
    return b"%d 0 obj\n" % num + body + b"\nendobj\n"


def _info_dict(metadata: dict) -> bytes:
    out = bytearray(b"<<")
    for key, field in (
        (b"Title", "title"),
        (b"Author", "author"),
        (b"Subject", "subject"),
        (b"Keywords", "keywords"),
    ):
        value = metadata.get(field)
        if value:
            out += b"/" + key + _pdf_text(value)
    out += b"/CreationDate" + _pdf_date(_timestamp(metadata, "created"))
    out += b"/ModDate" + _pdf_date(_timestamp(metadata, "modified"))
    out += b">>"
    return bytes(out)


def _xmp_object(num: int, metadata: dict) -> bytes:
    packet = _xmp_packet(metadata).encode("utf-8")
    head = b"<</Type/Metadata/Subtype/XML/Length %d>>" % len(packet)
    return (
        b"%d 0 obj\n" % num
        + head
        + b"\nstream\n"
        + packet
        + b"\nendstream\nendobj\n"
    )


def _xmp_packet(metadata: dict) -> str:
    created = _xmp_date(_timestamp(metadata, "created"))
    modified = _xmp_date(_timestamp(metadata, "modified"))
    body = [
        "   <dc:format>application/pdf</dc:format>",
    ]
    if metadata.get("title"):
        body.append(_xmp_alt("dc:title", metadata["title"]))
    if metadata.get("author"):
        body.append(_xmp_seq("dc:creator", metadata["author"]))
    if metadata.get("subject"):
        body.append(_xmp_alt("dc:description", metadata["subject"]))
    if metadata.get("language"):
        body.append(_xmp_bag("dc:language", metadata["language"]))
    if metadata.get("keywords"):
        body.append(f"   <pdf:Keywords>{_xml(metadata['keywords'])}</pdf:Keywords>")
    body.append(f"   <xmp:CreateDate>{created}</xmp:CreateDate>")
    body.append(f"   <xmp:ModifyDate>{modified}</xmp:ModifyDate>")
    body.append(f"   <xmp:MetadataDate>{modified}</xmp:MetadataDate>")

    namespaces = " ".join(f'xmlns:{k}="{v}"' for k, v in _XMP_NS.items())
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        f'  <rdf:Description rdf:about="" {namespaces}>\n'
        + "\n".join(body)
        + "\n  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>\n'
    )


def _xmp_alt(tag: str, value: str) -> str:
    return (
        f"   <{tag}>\n    <rdf:Alt>\n"
        f'     <rdf:li xml:lang="x-default">{_xml(value)}</rdf:li>\n'
        f"    </rdf:Alt>\n   </{tag}>"
    )


def _xmp_seq(tag: str, value: str) -> str:
    return (
        f"   <{tag}>\n    <rdf:Seq>\n"
        f"     <rdf:li>{_xml(value)}</rdf:li>\n"
        f"    </rdf:Seq>\n   </{tag}>"
    )


def _xmp_bag(tag: str, value: str) -> str:
    return (
        f"   <{tag}>\n    <rdf:Bag>\n"
        f"     <rdf:li>{_xml(value)}</rdf:li>\n"
        f"    </rdf:Bag>\n   </{tag}>"
    )


def _xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _patch_catalog(catalog: bytes, meta_num: int | None, metadata: dict) -> bytes:
    out = catalog
    if meta_num is not None:
        replacement = b"/Metadata %d 0 R" % meta_num
        if re.search(rb"/Metadata\s+\d+\s+\d+\s+R\b", out):
            out = re.sub(rb"/Metadata\s+\d+\s+\d+\s+R\b", replacement, out, count=1)
        else:
            out = out[:2] + replacement + out[2:]

    language = metadata.get("language")
    if language:
        replacement = b"/Lang" + _pdf_literal(language)
        pattern = rb"/Lang\s*(?:\([^)]*\)|<[0-9A-Fa-f\s]*>)"
        if re.search(pattern, out):
            out = re.sub(pattern, replacement, out, count=1)
        else:
            out = out[:2] + replacement + out[2:]

    if metadata.get("title"):
        out = _ensure_display_doc_title(out)
    return out


def _ensure_display_doc_title(catalog: bytes) -> bytes:
    m = re.search(rb"/ViewerPreferences\s*<<", catalog)
    if m is None:
        if re.search(rb"/ViewerPreferences\s+\d+\s+\d+\s+R\b", catalog):
            return catalog
        return catalog[:2] + b"/ViewerPreferences<</DisplayDocTitle true>>" + catalog[2:]
    prefs = _balanced_dict(catalog, m.end() - 2)
    if prefs is None or b"/DisplayDocTitle" in prefs:
        return catalog
    return catalog[:m.end()] + b"/DisplayDocTitle true" + catalog[m.end():]


def _timestamp(metadata: dict, field: str) -> dt.datetime:
    from .docx.document import parse_meta_datetime

    raw = metadata.get(field)
    if not raw:
        return NEUTRAL_TIMESTAMP
    return parse_meta_datetime(raw) or NEUTRAL_TIMESTAMP


def _pdf_text(value: str) -> bytes:
    encoded = "﻿" + value
    return b"<" + encoded.encode("utf-16-be").hex().upper().encode("ascii") + b">"


def _pdf_literal(value: str) -> bytes:
    escaped = value.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return b"(" + escaped.encode("ascii", "replace") + b")"


def _pdf_date(value: dt.datetime) -> bytes:
    return b"(D:" + value.strftime("%Y%m%d%H%M%S").encode("ascii") + b"+00'00')"


def _xmp_date(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_update(
    data: bytes,
    objects: list[tuple[int, bytes]],
    *,
    xref: _Xref,
    info_num: int,
    doc_id: bytes,
) -> bytes:
    out = bytearray(data)
    if not out.endswith(b"\n"):
        out += b"\n"

    offsets: dict[int, int] = {}
    for num, body in objects:
        offsets[num] = len(out)
        out += body

    size = max(xref.size, max(offsets) + 1)
    if xref.kind == "table":
        xref_offset = len(out)
        out += _xref_table(offsets)
        out += _trailer(
            size=size, root=xref.root_num, info=info_num,
            doc_id=doc_id, prev=xref.offset,
        )
    else:
        xref_num = size
        size += 1
        xref_offset = len(out)
        offsets[xref_num] = xref_offset
        out += _xref_stream(
            xref_num, offsets, size=size, root=xref.root_num,
            info=info_num, doc_id=doc_id, prev=xref.offset,
        )

    out += b"startxref\n%d\n" % xref_offset
    out += b"%%EOF\n"
    return bytes(out)


def _runs(numbers: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for num in numbers:
        if groups and num == groups[-1][-1] + 1:
            groups[-1].append(num)
        else:
            groups.append([num])
    return groups


def _xref_table(offsets: dict[int, int]) -> bytes:
    out = bytearray(b"xref\n0 1\n0000000000 65535 f \n")
    for group in _runs(sorted(offsets)):
        out += b"%d %d\n" % (group[0], len(group))
        for num in group:
            out += b"%010d 00000 n \n" % offsets[num]
    return bytes(out)


def _trailer(*, size: int, root: int, info: int, doc_id: bytes, prev: int) -> bytes:
    return (
        b"trailer\n<</Size %d/Root %d 0 R/Info %d 0 R/ID [<%s><%s>]/Prev %d>>\n"
        % (size, root, info, doc_id, doc_id, prev)
    )


def _xref_stream(
    num: int,
    offsets: dict[int, int],
    *,
    size: int,
    root: int,
    info: int,
    doc_id: bytes,
    prev: int,
) -> bytes:
    index = bytearray()
    payload = bytearray()
    for group in _runs(sorted(offsets)):
        index += b"%d %d " % (group[0], len(group))
        for entry in group:
            payload += b"\x01" + offsets[entry].to_bytes(4, "big") + b"\x00\x00"

    head = (
        b"<</Type/XRef/Size %d/Index[%s]/W[1 4 2]/Root %d 0 R/Info %d 0 R"
        b"/ID [<%s><%s>]/Prev %d/Length %d>>"
        % (size, bytes(index).strip(), root, info, doc_id, doc_id, prev, len(payload))
    )
    return (
        b"%d 0 obj\n" % num
        + head
        + b"\nstream\n"
        + bytes(payload)
        + b"\nendstream\nendobj\n"
    )
