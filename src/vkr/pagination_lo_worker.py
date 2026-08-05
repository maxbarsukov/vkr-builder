from __future__ import annotations

import json
import os
import re
import sys


def _clean(s: str) -> str:
    s = (s or "").replace("\x07", "")
    return s.replace("\r", "").replace("\n", "").replace("\x0b", "").strip()


def _paragraph_text(scan) -> str:
    try:
        saved = scan.getStart()
        scan.gotoStartOfParagraph(False)
        scan.gotoEndOfParagraph(True)
        text = str(scan.getString())
        scan.gotoRange(saved, False)
        cleaned = _clean(text)
        if cleaned:
            return cleaned
    except Exception:
        pass
    try:
        return _clean(str(scan.getString()))
    except Exception:
        return ""


_TOC_TAB_PAGE = re.compile(r"\t\d+$")


def _skip_paragraph_style(style_name: str) -> bool:
    sn = (style_name or "").strip()
    if sn in _skip_paragraph_styles():
        return True
    low = sn.lower()
    return low.startswith("toc")


def _is_toc_line(text: str) -> bool:
    return bool(_TOC_TAB_PAGE.search(text or ""))


def _heading_title(text: str) -> str:
    return _TOC_TAB_PAGE.sub("", text or "").strip()


_SKIP_PARAGRAPH_STYLES_DEFAULT = frozenset(
    {
        "ДИПЛОМ - Заголовок",
        "ДИПЛОМ - Обычный текст",
        "ДИПЛОМ - Рисунки",
        "ДИПЛОМ - Таблицы",
        "ДИПЛОМ - Код",
        "List Paragraph",
        "toc 1",
        "toc 2",
        "toc 3",
        "Normal",
        "Footer",
    }
)


def _skip_paragraph_styles() -> frozenset[str]:
    raw = os.environ.get("VKR_SKIP_PARAGRAPH_STYLES")
    if not raw:
        return _SKIP_PARAGRAPH_STYLES_DEFAULT
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _SKIP_PARAGRAPH_STYLES_DEFAULT
    if not isinstance(parsed, list):
        return _SKIP_PARAGRAPH_STYLES_DEFAULT
    return frozenset(str(x) for x in parsed)


def _heading_level(para, style_name: str) -> int | None:
    if _skip_paragraph_style(style_name):
        return None
    sn = (style_name or "").strip()
    for prefix in ("Heading ", "Заголовок "):
        if sn.startswith(prefix):
            try:
                return int(sn.rsplit(" ", 1)[-1])
            except ValueError:
                pass
    try:
        ol = int(para.getPropertyValue("OutlineLevel"))
    except Exception:
        ol = 10
    if ol >= 9:
        return None
    if 1 <= ol <= 3:
        return ol
    if 0 <= ol <= 2:
        return ol + 1
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: pagination_lo_worker.py DOCX_PATH", file=sys.stderr)
        return 2

    docx_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(docx_path):
        print(f"file not found: {docx_path}", file=sys.stderr)
        return 2

    import uno
    from com.sun.star.beans import PropertyValue

    def prop(name, value):
        p = PropertyValue()
        p.Name = name
        p.Value = value
        return p

    local_ctx = uno.getComponentContext()
    socket_port = os.environ.get("LIBREOFFICE_SOCKET")
    if socket_port:
        resolver = local_ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local_ctx
        )
        ctx = resolver.resolve(
            f"uno:socket,host=127.0.0.1,port={socket_port};urp;StarOffice.ComponentContext"
        )
        sm = ctx.ServiceManager
        desktop = sm.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    else:
        sm = local_ctx.ServiceManager
        desktop = sm.createInstanceWithContext("com.sun.star.frame.Desktop", local_ctx)

    url = uno.systemPathToFileUrl(docx_path)
    doc = desktop.loadComponentFromURL(
        url,
        "_blank",
        0,
        (prop("Hidden", True), prop("ReadOnly", True)),
    )
    if doc is None:
        print("failed to open document", file=sys.stderr)
        return 1

    collected: list[dict] = []
    try:
        controller = doc.getCurrentController()
        view_cursor = controller.getViewCursor()
        text = doc.getText()
        scan = text.createTextCursor()

        scan.gotoStart(False)
        while True:
            try:
                style_name = str(scan.getPropertyValue("ParaStyleName"))
            except Exception:
                style_name = ""
            try:
                text_content = _paragraph_text(scan)
            except Exception:
                text_content = ""
            text_clean = text_content
            if _skip_paragraph_style(style_name) or _is_toc_line(text_clean):
                if not scan.gotoNextParagraph(False):
                    break
                continue
            level = _heading_level(scan, style_name)
            if level is not None and text_clean:
                try:
                    view_cursor.gotoRange(scan.getStart(), False)
                    pg = int(view_cursor.getPage())
                except Exception:
                    pg = None
                if pg is not None:
                    collected.append(
                        {
                            "level": level,
                            "text": _heading_title(text_clean),
                            "page": pg,
                        }
                    )
            if not scan.gotoNextParagraph(False):
                break

        expected_start = os.environ.get("VKR_EXPECTED_PAGE_ONE")
        if expected_start is not None and collected:
            try:
                expected_val = int(expected_start)
                scan = text.createTextCursor()
                scan.gotoStart(False)
                view_cursor.gotoRange(scan.getStart(), False)
                physical_start = int(view_cursor.getPage())
                offset = expected_val - physical_start
                if offset != 0:
                    for item in collected:
                        item["page"] = int(item["page"]) + offset
            except (TypeError, ValueError):
                pass

        if not collected and os.environ.get("VKR_LO_DEBUG"):
            debug: list[dict] = []
            scan = text.createTextCursor()
            scan.gotoStart(False)
            while len(debug) < 40:
                try:
                    style_name = str(scan.getPropertyValue("ParaStyleName"))
                except Exception:
                    style_name = ""
                try:
                    ol = int(scan.getPropertyValue("OutlineLevel"))
                except Exception:
                    ol = -1
                try:
                    snippet = _paragraph_text(scan)[:60]
                except Exception:
                    snippet = ""
                debug.append({"style": style_name, "outline": ol, "text": snippet})
                if not scan.gotoNextParagraph(False):
                    break
            print(json.dumps(debug, ensure_ascii=True), file=sys.stderr)
    finally:
        try:
            doc.close(True)
        except Exception:
            pass

    print(json.dumps(collected, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
