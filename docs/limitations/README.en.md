# Limitations

| en :gb: | ru :ru: |
| ---- | ---- |
| README.en.md | [README.md](README.md) |

Known limitations of **vkr-builder**.

## Table of contents and PDF

- Accurate TOC page numbers require Microsoft Word (Windows) or LibreOffice with
  UNO. Without either engine, pagination falls back and TOC pages may be wrong.
- PDF export uses the same external engines; there is no built-in PDF renderer.
- Formulas in the PDF are drawn by a separate component of the engine. Without
  it — on Debian and Ubuntu that is `libreoffice-math`, which does not come with
  `libreoffice-writer` — a formula disappears silently: the `(1)` number stays,
  the formula does not, and nothing warns.

## Title page and front matter

- The builder does **not** generate a GOST title page, assignment sheet, or
  annotation block. Add those in Word after export if your university requires
  them. At ITMO they are generated automatically in [my.itmo.ru](https://my.itmo.ru/).

## Tables and layout

- Merged table cells are not supported in Markdown input.
- Long tables are split automatically: a «Продолжение таблицы N» caption is
  printed over each carried-over part (per GOST 7.32-2017) and the header row
  repeats on every page. The break point is found by the layout engine (Word
  COM or LibreOffice UNO), so continuation captions are skipped when no engine
  is available. Disable with `style.tables.continuation: false`.
- A file pulled in with `@listing` is read as UTF-8. A binary file, or one in
  another encoding, is a `listing-file` error and no listing reaches the document.
- Long listings are **not** split with a «Продолжение листинга N» caption;
  unlike tables, code block page breaks via the layout engine are not supported
  and are not planned.
- Table-continuation performance scales with the number of long split tables:
  break points are found by the layout engine over several passes, so more
  long tables mean more engine round-trips and slower builds. Disable with
  `style.tables.continuation: false` when building many long tables.
- References inside table cells and captions are printed as a number without a
  hyperlink. The number is right — it names the source, figure or table meant —
  but unlike the same reference in a paragraph it cannot be clicked.
- Orphan and widow line detection (`diagnose --no-orphans` skips this) needs
  Word COM on Windows or LibreOffice; it is best-effort and may report false
  positives on very short paragraphs.

## Language

- The tool targets a Russian-language thesis under GOST. The words `Рисунок`,
  `Таблица`, `Листинг`, `ПРИЛОЖЕНИЕ` and inflected forms such as «в приложении Б»
  are fixed by the standard and built into the parser. There is no translation
  to another language.

## Fonts

- Output uses fonts installed on the build machine. Bundled font files are not
  shipped; PDF/DOCX appearance may differ on another computer.
- Pagination depends on the fonts too. Without Times New Roman the engine
  substitutes the metric-compatible Liberation Serif, but line spacing derives
  from different vertical metrics, so page numbers drift from a build made on
  another machine — and so do the numbers in the table of contents.

## Diagnostics

- Post-build diagnostics inspect paragraph text and embedded drawing counts. They
  cannot catch every layout problem Word might show on screen.
