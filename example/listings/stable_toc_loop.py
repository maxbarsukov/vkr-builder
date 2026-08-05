def build_with_stable_toc(elements, render, paginate, max_passes=5):
    """Build a DOCX until the table-of-contents page numbers settle.

    The page number of a heading depends on the layout, and the layout
    depends on the table of contents, so the only reliable way to fill in
    real page numbers is to render, measure, and repeat until nothing moves.
    """
    page_numbers = {}
    previous = None
    for attempt in range(1, max_passes + 1):
        document = render(elements, page_numbers)
        document.save("_draft.docx")

        measured = paginate("_draft.docx")
        if measured == previous:
            # Page numbers are stable: the current draft is final.
            document.save("final.docx")
            return attempt

        # Feed the freshly measured numbers into the next pass so the table
        # of contents reflects the real layout instead of placeholders.
        previous = measured
        page_numbers = dict(measured)

    # Numbers never settled; keep the last draft but report the problem so
    # the caller can decide whether the result is good enough.
    document.save("final.docx")
    raise RuntimeError(
        f"table of contents did not stabilize after {max_passes} passes"
    )


def collect_headings(elements):
    """Pull the headings out of the parsed elements in document order."""
    headings = []
    for index, element in enumerate(elements):
        if element["type"] != "heading":
            continue
        headings.append(
            {
                "level": element["level"],
                "text": element["text"].strip(),
                "order": index,
            }
        )
    return headings
