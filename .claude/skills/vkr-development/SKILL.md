---
name: vkr-development
description: Work on the vkr-builder codebase itself — add or change a command, a check, a warning, or the console output. Use when editing anything under src/vkr/, adding tests, or wondering where a piece of behaviour belongs.
---

# Working on the code

```
src/vkr/
  cli.py            commands: parse, orchestrate, render the report
  ui.py             the only module that writes to the user
  progress.py       build phases as console steps
  logging_setup.py  logging -> findings bridge
  suppress.py       rule names and @suppress directives
  engines.py        Word / LibreOffice detection, "auto"
  md.py, md_lint.py markdown parsing and checks
  docx/             document building
  pagination.py     Word COM and LibreOffice UNO
src/tests/          pytest, run with: python -m pytest src/tests
```

## The output rules

- **`ui.py` is the only place that writes to a stream.** A module that wants
  to tell the user something calls `log.warning(...)`; the handler in
  `logging_setup.py` turns it into a finding. Never `print()`, never write
  to `sys.stderr` from a library module.
- Give a user-facing warning a rule so it can be suppressed and looked up:

  ```python
  log.warning("could not insert image %s: %s", path, exc,
              extra={"rule": "image"})
  ```

  and add that name to `suppress.RULES` with a one-line meaning — a test
  fails if a rule is used but not documented.
- Message style: lower-case opening, no trailing period, no module prefix
  (`unknown reference [рис:k]`, not `Crossref: Unknown reference.`).
- Widths are terminal columns, not code points: use `ui.text_width` and
  `ui._pad`, never `len()` or `ljust()`, for anything that lines up. A glyph
  the terminal draws two columns wide (any emoji) breaks every column after
  it — there is a test guarding the status glyphs.
- Body text keeps the terminal's own colour; colour is only for status
  glyphs, the title and paths, so the report reads on light and dark themes.

## Commands

Each command in `cli.py` follows the same shape: header with context,
steps/findings, then exactly one footer (`footer_ok` / `footer_warn` /
`footer_fail`). Resolve the engine once through `_engine(cfg, args)` and put
the label in the header. Argparse never prints its own usage: `-h` and
errors go through this module's renderer.

## Tests

- `python -m pytest src/tests` — the whole suite, a couple of minutes with
  Word on Windows.
- UI behaviour is tested by rendering into a `StringIO` console (see
  `src/tests/test_ui.py`), including the live region with a fake TTY. Assert
  on columns and shapes, not on exact colour codes.
- A change to the report is not done until the sample in both READMEs matches
  what the tool actually prints.

## Working habits in this repo

- Do not commit `_bundle.md` or `*.preview.docx`.
- After changing the build, run it for real (`vkr-builder.bat build`) as
  well as the suite: the Word and LibreOffice paths are not covered by unit
  tests.
