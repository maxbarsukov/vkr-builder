from __future__ import annotations

import json
import os
import sys
import time


def _connect(local_ctx, port: str):
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx
    )
    url = (
        f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext"
    )
    last_exc = None
    for _ in range(40):
        try:
            return resolver.resolve(url)
        except Exception as exc:
            last_exc = exc
            time.sleep(0.25)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("could not connect to LibreOffice")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: pagination_lo_tables_worker.py DOCX_PATH", file=sys.stderr)
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
        ctx = _connect(local_ctx, socket_port)
        sm = ctx.ServiceManager
        desktop = sm.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    else:
        sm = local_ctx.ServiceManager
        desktop = sm.createInstanceWithContext(
            "com.sun.star.frame.Desktop", local_ctx
        )

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

    out: list[list[int]] = []
    try:
        controller = doc.getCurrentController()
        view_cursor = controller.getViewCursor()
        tables = doc.getTextTables()

        for ti in range(tables.getCount()):
            table = tables.getByIndex(ti)
            try:
                repeat = bool(table.getPropertyValue("RepeatHeadline"))
            except Exception:
                repeat = False
            if not repeat:
                continue
            try:
                n_rows = int(table.getRows().getCount())
            except Exception:
                continue

            pages: list[int] = []
            for r in range(2, n_rows + 1):
                pg = None
                try:
                    cell = table.getCellByName("A%d" % r)
                    view_cursor.gotoRange(cell.getStart(), False)
                    pg = int(view_cursor.getPage())
                except Exception:
                    pg = None
                if pg is None:
                    pg = pages[-1] if pages else 1
                pages.append(pg)
            out.append(pages)
    finally:
        try:
            doc.close(True)
        except Exception:
            pass

    print(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
