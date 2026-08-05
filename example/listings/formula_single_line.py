import re

_SINGLE_LINE_DISPLAY_RE = re.compile(r"^\\\[(?P<body>.*?)\\\]$")


def parse_single_line_formula(line):
    m = _SINGLE_LINE_DISPLAY_RE.match(line.strip())
    return m.group("body").strip() if m else None
