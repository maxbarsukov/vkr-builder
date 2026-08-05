from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .state import W, _SECTPR_ORDER, _TBLPR_ORDER

def el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k), str(v))
    return e

def clear_body(doc):
    body = doc.element.body
    children = list(body)
    for child in children:
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)

def add_field(paragraph, instr_text):
    run = paragraph.add_run()
    fld_begin = el("w:fldChar", **{"w:fldCharType": "begin"})
    run._element.append(fld_begin)

    run2 = paragraph.add_run()
    instr = el("w:instrText", **{"xml:space": "preserve"})
    instr.text = " " + instr_text + " "
    run2._element.append(instr)

    run3 = paragraph.add_run()
    fld_sep = el("w:fldChar", **{"w:fldCharType": "separate"})
    run3._element.append(fld_sep)

    run4 = paragraph.add_run()
    fld_end = el("w:fldChar", **{"w:fldCharType": "end"})
    run4._element.append(fld_end)

    return run

def page_break_before(paragraph):
    pPr = paragraph._element.get_or_add_pPr()
    pbb = OxmlElement("w:pageBreakBefore")
    pPr.append(pbb)

def _insert_tblpr_child_in_order(tblPr, new_child):
    target_local = new_child.tag.split("}")[1]
    target_index = _TBLPR_ORDER.index(target_local)
    insert_at = None
    for i, ch in enumerate(list(tblPr)):
        local = ch.tag.split("}")[1]
        try:
            idx = _TBLPR_ORDER.index(local)
        except ValueError:
            continue
        if idx > target_index:
            insert_at = i
            break
    if insert_at is None:
        tblPr.append(new_child)
    else:
        tblPr.insert(insert_at, new_child)

def _insert_sectpr_child_in_order(sectPr, new_child):
    target_local = new_child.tag.split("}")[1]
    target_index = _SECTPR_ORDER.index(target_local)
    insert_at = None
    for i, ch in enumerate(list(sectPr)):
        local = ch.tag.split("}")[1]
        try:
            idx = _SECTPR_ORDER.index(local)
        except ValueError:
            continue
        if idx > target_index:
            insert_at = i
            break
    if insert_at is None:
        sectPr.append(new_child)
    else:
        sectPr.insert(insert_at, new_child)
