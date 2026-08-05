# Check rules

| en :gb: | ru :ru: |
| ---- | ---- |
| README.en.md | [README.md](README.md) |

Every finding carries a **rule name**, and the name does not change when the
wording of the message does. It appears in `--json` as `rule`, and it is what
you write in an `@suppress` directive — see [Markdown format rules](../llm-format/README.en.md).

Rules are grouped by stage, and the stage decides which command reports them.

## Markdown — `lint`, and the pre-flight inside `build` and `watch`

| Rule | Finding | What to do |
|------|---------|------------|
| `unknown-reference` | a `[рис:key]` reference with no caption to point at | add the caption, or fix the key |
| `unknown-citation` | a citation the source list does not define | add the source, or fix the number/key |
| `duplicate-key` | one key on two objects | rename one |
| `uncited-source` | a source nobody cites | cite it or remove it |
| `unreferenced-object` | a figure, table or listing nothing refers to | add `[рис:key]` in the text |
| `caption-order` | a caption on the wrong side of its object | figures after, tables and listings before |
| `caption-spacing` | an image and its caption glued into one paragraph | separate them with a blank line, or the figure never reaches the document |
| `comma-citation` | the `[1, 2]` form | GOST wants `[1; 2]` |
| `spaced-range` | a range with spaces: `6 - 7` | close the gap — `6-7`; if the spacing is deliberate, silence it with a directive |
| `table-columns` | a row with a different column count than the header | even out the columns |
| `long-paragraph` | a paragraph past the length limit | split it |
| `empty-section` | a heading with no body text | write the section |
| `structural-heading` | a level-1 heading that is not a GOST section name | fix the section name |
| `numbering-gap` | a gap in explicit object numbers | number by key instead of by hand |
| `dictionary-order` | abbreviations or terms out of alphabetical order | sort them, or set `build.sort_dictionary_lists` |
| `appendix-letter` | an invalid or repeated appendix letter | **I**, **O** and **Ё З Й О Ч Ь Ы Ъ** are not allowed |
| `listing-file` | an `@listing` file that cannot be read, or is empty | check the path relative to `listings_dir` and the line range |

## Build — while the document is written

| Rule | Finding | What to do |
|------|---------|------------|
| `unknown-key` | a caption or formula key nothing defines | define it, or drop the braces |
| `duplicate-source` | the same source number or key twice | keep one entry |
| `image` | an image that could not be read or inserted | check the path against `images_dir` |
| `metadata` | a `metadata` value that would not parse | dates: `2026-01-15` or `2026-01-15 10:30:00` |
| `table-continuation` | a table that could not be split across pages | usually a cell taller than a page |
| `toc-unstable` | page numbers that never settled | worth reporting: almost always a layout loop |
| `heading-mismatch` | document headings differ from the markdown | rebuild without `--skip-merge` |
| `page-numbering` | the printed first page number is not the configured one | check `style.page.number_from` |
| `output-locked` | the output file is held open by another program | close the DOCX in Word; the build saves a `-new` copy |
| `unknown-element` | markup the builder does not know | see [Markdown format rules](../llm-format/README.en.md) |

Four rules belong to both stages — `unknown-reference`, `unknown-citation`,
`uncited-source` and `listing-file`. The linter finds them in the markdown and the builder meets
them again while writing, so a directive naming one of them is only called
useless after a full build, never after `lint` alone.

## Finished document — `diagnose` and `build --diagnose`

| Rule | Finding | What to do |
|------|---------|------------|
| `figure-captions` | figures and their captions do not add up | check every figure has one |
| `table-captions` | table captions do not add up | the same for tables |
| `empty-heading` | a heading with no text | write it or drop it |
| `orphan-widow` | a line left alone at a page boundary | fix by rewording; the check is best-effort |

## Related docs

- [Markdown format rules](../llm-format/README.en.md) — markup rules and the `@suppress` directive
- [Limitations](../limitations/README.en.md) — what the tool does not do
