import datetime as dt
import os
import re
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement, parse_xml
from docx.opc.oxml import serialize_part_xml
from docx.oxml.ns import qn
from docx.shared import Cm

from .. import docx_style
from ..config import NEUTRAL_TIMESTAMP
from ..docx_style import create_vkr_document, font_half_points, style_id
from ..logging_setup import get_logger
from .ooxml import _insert_sectpr_child_in_order
from .state import log

log = get_logger("docx")

def resolve_image_path(path: str, assets_root: Path | None) -> str:
    if assets_root is None:
        return path
    normalized = path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    while parts and parts[0] == "..":
        parts.pop(0)
    if parts and parts[0].lower() == assets_root.name.lower():
        return str(assets_root.joinpath(*parts[1:]))
    if parts:
        candidate = assets_root.joinpath(*parts)
        if candidate.is_file():
            return str(candidate)
    candidate = assets_root / Path(normalized).name
    if candidate.is_file():
        return str(candidate)
    return path

def setup_section_and_footer(doc):
    section = doc.sections[0]
    section.page_width = Cm(docx_style.PAGE_WIDTH_CM)
    section.page_height = Cm(docx_style.PAGE_HEIGHT_CM)
    section.left_margin = Cm(docx_style.MARGIN_LEFT_CM)
    section.right_margin = Cm(docx_style.MARGIN_RIGHT_CM)
    section.top_margin = Cm(docx_style.MARGIN_TOP_CM)
    section.bottom_margin = Cm(docx_style.MARGIN_BOTTOM_CM)
    section.header_distance = Cm(docx_style.HEADER_DISTANCE_CM)
    section.footer_distance = Cm(docx_style.FOOTER_DISTANCE_CM)

    section.different_first_page_header_footer = False
    sectPr = section._sectPr
    for ref in list(sectPr.findall(qn("w:footerReference"))):
        sectPr.remove(ref)
    for ref in list(sectPr.findall(qn("w:headerReference"))):
        sectPr.remove(ref)

    for pgnum in list(sectPr.findall(qn("w:pgNumType"))):
        sectPr.remove(pgnum)
    pgnum = OxmlElement("w:pgNumType")
    pgnum.set(qn("w:start"), str(int(docx_style.PAGE_NUMBERING_DISPLAY_START)))
    _insert_sectpr_child_in_order(sectPr, pgnum)

    for tp in list(sectPr.findall(qn("w:titlePg"))):
        sectPr.remove(tp)

    return section

def write_footer_part(doc):
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.parts.hdrftr import FooterPart
    hp = font_half_points(docx_style.FOOTER_PAGE_FONT_PT)
    ff = docx_style.FONT_FAMILY
    rf = f'w:ascii="{ff}" w:hAnsi="{ff}" w:cs="{ff}" w:eastAsia="{ff}"'
    footer_style_id = style_id(doc, docx_style.STYLE_FOOTER)
    footer_xml = f'''<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
       xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
  <w:p>
    <w:pPr>
      <w:pStyle w:val="{footer_style_id}"/>
      <w:jc w:val="center"/>
      <w:rPr>
        <w:rFonts {rf}/>
        <w:color w:val="000000"/>
        <w:sz w:val="{hp}"/>
        <w:szCs w:val="{hp}"/>
        <w:b w:val="0"/><w:bCs w:val="0"/>
      </w:rPr>
    </w:pPr>
    <w:r>
      <w:rPr>
        <w:rFonts {rf}/>
        <w:color w:val="000000"/>
        <w:sz w:val="{hp}"/>
        <w:szCs w:val="{hp}"/>
        <w:b w:val="0"/><w:bCs w:val="0"/>
      </w:rPr>
      <w:fldChar w:fldCharType="begin"/>
    </w:r>
    <w:r>
      <w:rPr>
        <w:rFonts {rf}/>
        <w:color w:val="000000"/>
        <w:sz w:val="{hp}"/>
        <w:szCs w:val="{hp}"/>
        <w:b w:val="0"/><w:bCs w:val="0"/>
      </w:rPr>
      <w:instrText xml:space="preserve"> PAGE   \\* MERGEFORMAT </w:instrText>
    </w:r>
    <w:r>
      <w:rPr>
        <w:rFonts {rf}/>
        <w:color w:val="000000"/>
        <w:sz w:val="{hp}"/>
        <w:szCs w:val="{hp}"/>
        <w:b w:val="0"/><w:bCs w:val="0"/>
      </w:rPr>
      <w:fldChar w:fldCharType="separate"/>
    </w:r>
    <w:r>
      <w:rPr>
        <w:rFonts {rf}/>
        <w:color w:val="000000"/>
        <w:sz w:val="{hp}"/>
        <w:szCs w:val="{hp}"/>
        <w:b w:val="0"/><w:bCs w:val="0"/>
      </w:rPr>
      <w:t>3</w:t>
    </w:r>
    <w:r>
      <w:rPr>
        <w:rFonts {rf}/>
        <w:color w:val="000000"/>
        <w:sz w:val="{hp}"/>
        <w:szCs w:val="{hp}"/>
        <w:b w:val="0"/><w:bCs w:val="0"/>
      </w:rPr>
      <w:fldChar w:fldCharType="end"/>
    </w:r>
  </w:p>
</w:ftr>'''

    for rel in doc.part.rels.values():
        if rel.reltype == RELATIONSHIP_TYPE.FOOTER:
            footer_elem = parse_xml(footer_xml)
            rel.target_part._element = footer_elem
            try:
                rel.target_part._blob = footer_xml.encode("utf-8")
            except AttributeError:
                pass
            return rel.rId

    footer_part = FooterPart.new(doc.part.package)
    footer_elem = parse_xml(footer_xml)
    footer_part._element = footer_elem
    doc.part.package.parts.append(footer_part) if hasattr(doc.part.package, 'parts') else None
    rId = doc.part.relate_to(footer_part, RELATIONSHIP_TYPE.FOOTER)
    return rId

def link_footer_to_section(doc, rId):
    section = doc.sections[0]
    sectPr = section._sectPr
    for ref in list(sectPr.findall(qn("w:footerReference"))):
        sectPr.remove(ref)
    ref = OxmlElement("w:footerReference")
    ref.set(qn("w:type"), "default")
    ref.set(qn("r:id"), rId)
    _insert_sectpr_child_in_order(sectPr, ref)

def _blank_extended_app_properties_blob(blob: bytes) -> bytes | None:
    if not blob:
        return None
    try:
        root = parse_xml(blob)
    except Exception:
        return None
    bool_tags = frozenset(
        {"ScaleCrop", "LinksUpToDate", "SharedDoc", "HyperlinksChanged"}
    )
    zero_tags = frozenset(
        {
            "TotalTime",
            "Pages",
            "Words",
            "Characters",
            "CharactersWithSpaces",
            "Lines",
            "Paragraphs",
            "DocSecurity",
        }
    )
    skip_complex = frozenset({"HeadingPairs", "TitlesOfParts"})
    for child in root.iterchildren():
        tag_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag_local in skip_complex:
            continue
        if len(child) > 0:
            continue
        if tag_local == "AppVersion":
            child.text = "15.0000"
            continue
        if tag_local in bool_tags:
            child.text = "false"
        elif tag_local in zero_tags:
            child.text = "0"
        else:
            child.text = ""
    return serialize_part_xml(root)

def parse_meta_datetime(value: str) -> dt.datetime | None:
    text = value.strip()
    parsed = None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        log.warning(
            "could not parse metadata date %r; leaving it neutral",
            value,
            extra={"rule": "metadata"},
        )
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed

def apply_document_metadata(doc: Document, metadata: dict | None) -> None:
    strip_document_metadata(doc)
    if not metadata:
        return

    cp = doc.core_properties
    str_fields = (
        "title", "author", "subject", "keywords", "category",
        "comments", "language", "last_modified_by",
    )
    for field in str_fields:
        val = metadata.get(field)
        if val:
            try:
                setattr(cp, field, val)
            except Exception:
                log.warning(
                    "could not set document metadata: %s",
                    field,
                    extra={"rule": "metadata"},
                )
    for field in ("created", "modified"):
        val = metadata.get(field)
        if val:
            parsed = parse_meta_datetime(val)
            if parsed is not None:
                try:
                    setattr(cp, field, parsed)
                except Exception:
                    log.warning(
                        "could not set document metadata: %s",
                        field,
                        extra={"rule": "metadata"},
                    )

def package_timestamp(metadata: dict | None) -> dt.datetime:
    raw = (metadata or {}).get("modified")
    return (parse_meta_datetime(raw) if raw else None) or NEUTRAL_TIMESTAMP


def normalise_package_timestamps(path: str | Path, when: dt.datetime) -> None:
    path = Path(path)
    stamp = (when.year, when.month, when.day, when.hour, when.minute, when.second)
    if when.year < 1980:
        stamp = (1980, 1, 1, 0, 0, 0)
    tmp = path.with_name(path.name + ".vkr-tmp")
    try:
        with zipfile.ZipFile(path) as src:
            entries = [(info, src.read(info.filename)) for info in src.infolist()]
        with zipfile.ZipFile(tmp, "w") as dst:
            for info, blob in entries:
                fixed = zipfile.ZipInfo(info.filename, stamp)
                fixed.compress_type = info.compress_type
                fixed.external_attr = info.external_attr
                fixed.internal_attr = info.internal_attr
                fixed.create_system = info.create_system
                dst.writestr(fixed, blob)
        os.replace(tmp, path)
    except (OSError, zipfile.BadZipFile) as exc:
        log.warning(
            "could not give the DOCX a fixed date: %s",
            exc,
            extra={"rule": "metadata"},
        )
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def strip_document_metadata(doc: Document) -> None:
    neutral = NEUTRAL_TIMESTAMP

    cp = doc.core_properties
    for attr in (
        "author",
        "category",
        "comments",
        "content_status",
        "identifier",
        "keywords",
        "language",
        "last_modified_by",
        "subject",
        "title",
        "version",
    ):
        try:
            setattr(cp, attr, "")
        except Exception:
            pass
    try:
        cp.created = neutral
    except Exception:
        pass
    try:
        cp.modified = neutral
    except Exception:
        pass
    try:
        cp.last_printed = neutral
    except Exception:
        pass
    try:
        cp.revision = 1
    except Exception:
        pass

    pkg = doc.part.package
    try:
        app = pkg.part_related_by(RT.EXTENDED_PROPERTIES)
        new_blob = _blank_extended_app_properties_blob(app.blob)
        if new_blob is not None:
            app._blob = new_blob
    except (KeyError, AttributeError):
        pass
