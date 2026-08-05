---
name: vkr-findings
description: Diagnose and fix vkr-builder findings — lint errors, build warnings and diagnose issues — and decide when to silence one with @suppress. Use when a build or lint run reported warnings/errors, or when asked what a rule name means.
---

# Fixing what a run reported

A finding looks like this and always names the file the author edits:

```
    ✗ 04-chapter1.md:12  reference [рис:nope] has no matching figure caption
```

Every finding has a stable rule name (visible in `--json` as `rule`). Fix by
rule, not by wording — the wording can change, the rule does not.

## Markdown rules (`lint`, and the pre-flight inside `build`)

| Rule | Fix |
|------|-----|
| `unknown-reference` | add the caption with that `{key}`, or correct the key in the reference |
| `duplicate-key` | two objects share a key; rename one |
| `unknown-citation` | the cited source is missing from `# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ` |
| `uncited-source` | a listed source is never cited; cite it or remove it |
| `unreferenced-object` | a figure/table/listing nothing refers to; add `[рис:key]` in the text |
| `caption-order` | caption on the wrong side: figures after the image, tables and listings before the block |
| `caption-spacing` | the image and its caption are on adjacent lines — put a blank line between them, or the figure is lost |
| `comma-citation` | `[1, 2]` is not a GOST citation — write `[1; 2]` |
| `spaced-range` | a range set with spaces: `6 - 7` → `6-7`; suppress it if the spacing is deliberate |
| `table-columns` | a row has a different cell count than the header (error, blocks the build) |
| `long-paragraph` | split it |
| `empty-section` | a heading with no text under it |
| `structural-heading` | a level-1 heading that is not a GOST section name |
| `numbering-gap` | gap in explicit numbers; use `{key}` numbering instead |
| `dictionary-order` | sort the abbreviations/terms alphabetically (`build.sort_dictionary_lists: true` does it) |
| `appendix-letter` | invalid or repeated appendix letter (no I, O, Ё, З, Й, О, Ч, Ь, Ъ) |
| `listing-file` | the `@listing` file did not become a listing — see below |

`listing-file` is worth reading closely, because one rule covers several
causes and the message says which:

| Message | Fix |
|---------|-----|
| `file not found` | the path is relative to `listings_dir` (or `images_dir` when that key is unset), not to the Markdown file |
| `path escapes the listings directory` | the file lies outside the configured root; move it in or point the key at its parent |
| `no listings directory is configured` | the profile has neither `listings_dir` nor `images_dir` |
| `has N lines, range starts at M` | the range runs past the end of the file |
| `is numbered from 1, range starts at 0` | lines count from 1, not from 0 |
| `empty line range` | the right bound is below the left one |
| `is empty, nothing will be inserted` | a warning, not an error: the file exists but has no lines |
| `cannot read` | not UTF-8 text — a binary file or another encoding |

Do not suppress it. A silenced `listing-file` still produces an empty listing:
the caption and the number stay, the code does not, and the frame is missing
from the document without anything saying so.

## Build rules (raised while the document is written)

| Rule | Fix |
|------|-----|
| `unknown-key` | the `{key}` in a caption or formula is defined nowhere — define it or drop the braces |
| `duplicate-source` | the same source number or key twice in the list |
| `image` | the file is missing or unreadable; check the path against `images_dir` |
| `metadata` | a `metadata:` value in config could not be parsed (dates: `YYYY-MM-DD`) |
| `table-continuation` | a table could not be split across pages — usually a cell too tall to fit |
| `toc-unstable` | page numbers never settled; almost always a layout loop worth reporting |
| `heading-mismatch` | the document has different headings than the markdown — stale bundle or a manual edit |
| `page-numbering` | printed first page differs from `style.page.number_from` |
| `output-locked` | the DOCX is open in Word; the build saved a `-new` copy instead |
| `unknown-element` | markdown the builder does not know how to render |

## Document rules (`diagnose`, `build --diagnose`)

`figure-captions`, `table-captions`, `empty-heading`, `long-paragraph`,
`empty-section`, `orphan-widow` — these inspect the finished DOCX, so their
location is `paragraph N`, not a markdown line.

## Deciding: fix or suppress

Fix by default. Suppress only when the finding is **correct and intended** —
a chapter that quotes the reference syntax, a table that is meant to look
that way. Put the directive where the thing is, and name the rule:

```markdown
<!-- @suppress unknown-reference -->
```

- `<!-- @suppress -->` — everything about the next element.
- `<!-- @suppress-file rule -->` — the rest of the file.
- A pattern that matches no rule name falls back to matching the message
  text as a case-insensitive substring; prefer the rule name.
- Suppressed findings stay counted (`· 4 suppressed`) and stay in `--json`
  with `"suppressed": true`. A suppressed error does not fail the build.
- A directive that silences nothing is itself reported — remove it once the
  underlying finding is fixed.

## Flooding

A command prints at most ten warnings, then counts the rest; `-v` shows them
all. Errors are never withheld. If a report says `N not shown`, rerun with
`-v` before concluding anything about what is wrong.
