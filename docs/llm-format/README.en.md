# Markdown format rules for LLMs

| en :gb: | ru :ru: |
| ---- | ---- |
| README.en.md | [README.md](README.md) |

Compact specification of the Markdown dialect accepted by this tool. Follow it
exactly when generating thesis content. Output Markdown only; do not add HTML.

## Normative basis (ITMO)

Layout and structure follow ITMO standard **ЛНАОБУЧ-СМК-03-05-2022**
(*Требования к выпускным квалификационным работам*, version 4.0). Same
document, two URLs:

- [student.itmo.ru/files/1314](https://student.itmo.ru/files/1314)
- [edu.itmo.ru/files/345](https://edu.itmo.ru/files/345)

GOST 7.32-2017 is used as a structural reference for report sections and
bibliography ordering.

## Files and order

- Content lives in several `.md` files merged in the order listed under the
  active profile in `config.yaml` (`markdown_files`).
- One logical section per file is recommended (abbreviations, terms, intro,
  chapters, conclusion, sources, appendices).
- Blocks are separated by blank lines. A block is a paragraph, heading,
  list, table, code fence, image, caption, or formula.

## Headings

- `# Title` level 1, `## Title` level 2, `### Title` level 3.
- Numbered chapters: `# 1 Chapter name`, `## 1.1 Subsection`. Do not put a
  period after the chapter number in the `#` line.
- Structural sections use their canonical Russian names in upper case, e.g.
  `# СПИСОК СОКРАЩЕНИЙ И УСЛОВНЫХ ОБОЗНАЧЕНИЙ`,
  `# ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ`, `# ВВЕДЕНИЕ`, `# ЗАКЛЮЧЕНИЕ`,
  `# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ`, `# ПРИЛОЖЕНИЕ А`.
- Appendix headings: `# ПРИЛОЖЕНИЕ <LETTER>`. Avoid letters **I**, **O** and
  Cyrillic **Ё З Й О Ч Ь Ы Ъ** (ITMO/GOST rules).

## Dictionary sections

Under `# СПИСОК СОКРАЩЕНИЙ И УСЛОВНЫХ ОБОЗНАЧЕНИЙ` or `# ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ`,
write one entry per paragraph:

```text
AST – Abstract Syntax Tree, абстрактное синтаксическое дерево
API – Application Programming Interface, программный интерфейс
```

Use a spaced en-dash ` – ` or hyphen ` - ` between the term and the definition.
Latin-only terms sort before Cyrillic-only terms within the section.

## Paragraphs

- Plain text. Use a single blank line between paragraphs.
- Do not use bold for emphasis in body text; it is normalized away according to GOST.
- Set ranges of numbers and dates tight: `6-7`, `2025-2026 гг.` The build turns
  the dash into an en dash and keeps the spacing as typed — `6 - 7` is not read
  as a range, and the linter reports it as `spaced-range`.

## Captions and keys

Every numbered object gets a stable key in braces `{key}`. The tool replaces
the key with the running number at build time. Author captions like this:

```text
Рисунок {pipeline} - Caption text
Таблица {req} - Caption text
Листинг {block} - Caption text
```

- Put a figure caption in **its own block after** the image, separated by a
  blank line. Without it the image and the caption merge into one paragraph and
  the figure never reaches the document.
- Place a table or listing caption **before** the table or code block.
- The separator after the key is a hyphen or a dash; the build normalises it
  to whatever `style.dashes.captions` says (an en dash by default, as in the
  ITMO standard).
- Keys are unique per object kind: a figure and a table may share a key, two
  figures may not. Use short lowercase identifiers.

## Images

```markdown
![alt text](figure01.png)

Рисунок {pipeline} - Caption text

Порядок разбора показан на рисунке [рис:pipeline].
```

Paths are relative to `images_dir` from the config; do not repeat the
directory name in them. Subdirectories work: `diagrams/fig02.png`.

## Formulas

- Inline math: `\( ... \)`.
- Display math: `\[ ... \]` on its own block.
- To number a display formula, put a key line right after it:

```text
\[ N = \sum_{i=1}^{k} 1 \]
{count}
```

Supported LaTeX subset includes fractions `\frac{a}{b}`, sub/superscripts
`x_i`, `x^2`, big operators `\sum`, `\prod`, `\int` with limits, Greek
letters, and `\times`, `\%`, etc.

## Cross-references

Reference numbered objects with `[prefix:key]`; they render as the number
and become clickable links.

- Figure: `[рис:pipeline]` (synonyms: `pic`, `picture`, `image`, `fig`)
- Table: `[табл:req]` (synonym: `table`)
- Listing: `[лист:block]` (synonyms: `listing`, `code`)
- Formula: `[форм:count]` (synonyms: `eqn`, `formula`, `equation`, `eq`)

Always reference by key; never hard-code a number in cross-references.

## Citations

Pick one style per document and keep to it.

**Numeric.** Cite with square brackets: `[1]`, `[1; 2]`, `[1-3]`. The
bibliography is reordered by order of first mention and the numbers in the text
are remapped to match. Brackets holding an unknown number stay plain text
(`[2024]`). The comma form `[1, 2]` is not a citation under GOST and stays as
written. Escape literal brackets in prose: `\[note\]`, `\{key\}`.

**By key** — nothing to keep track of. Cite as `[{gost732}]`, several at once
with `;`: `[{markdown}; {ecma376}]`. This form has no ranges; list the keys. A
key is letters, digits, `_` and `-`.

Citing a key the list does not define fails the build (`unknown-citation`); an
entry nobody cites lands at the end of the list with a warning
(`uncited-source`).

Formula references in prose: `[форм:count]` or `Формула (1)` / `Formula (1)`.
Both become clickable links to the numbered formula.

## Source list

Section heading: `# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ`.

Numeric style — one source per paragraph or list item:

```text
1. Author A. Title. Publisher, 2024.
2. Author B. Another title. 2023.
```

Keyed style — each entry opens with its key and is **separated by a blank
line**. Without the blank line the entries merge into one paragraph and only
the first is found:

```markdown
{gost732} ГОСТ 7.32—2017. Отчёт о научно-исследовательской работе. – М.:
Стандартинформ, 2017. – 27 с.

{markdown} Gruber J. Markdown: Syntax. – URL:
https://daringfireball.net/projects/markdown (accessed 15.03.2026).
```

Numbers are assigned by order of first mention and the list is rebuilt in that
order, so how the entries sit in the file does not matter.

## Lists

- Dash items: lines starting with `- `.
- Numbered items: `1)` or `1.` (both render as `1)`).
- Lettered items: `а)` ... or `a)` ...
- Nested lists: indent the sub-items by two spaces. Example (GOST style):

```text
- first area:
  1) sub-item one;
  2) sub-item two;
- second area.
```

## Tables

Standard GitHub-style pipe tables, with the caption before the table:

```markdown
Таблица {metrics} - Показатели производительности

| Показатель | Значение |
|------------|---------:|
| Задержка   | 12 ms    |

Результаты сведены в таблице [табл:metrics].
```

Header column count must match every body row (linter error if not).

## Code listings

Fenced code blocks; precede with a `Листинг {key} - ...` caption when the
listing is referenced.

````markdown
Листинг {api} - Обработчик запроса

```python
def handle():
    return 200
```

Разбор показан в листинге [лист:api].
````

## Listing from a file

Instead of copying code into the Markdown, point at it. An `@listing` line is
replaced with the contents of the file:

```text
Листинг {parser} - Разбор блоков Markdown
@listing md.py
```

The path is relative to `listings_dir` from the config (when the key is unset,
`images_dir` is used). Escaping that directory is refused.

A fragment is given by line numbers after a colon; leave the right bound empty
to run to the end of the file:

```text
@listing md.py:582-607
@listing md.py:582-
```

The caption goes before `@listing`, as it does before an ordinary code block. A
file that cannot be read is a `listing-file` error; an empty one is a warning.
Inside a code block `@listing` stays plain text.

## Suppressing findings

When a finding is intentional - a chapter quoting the reference syntax
itself, a table that is meant to look that way - silence it with a directive
in an HTML comment. The comment never reaches the document.

```markdown
<!-- @suppress -->
Here [рис:k] is an example of the syntax, not a broken reference.
```

| Form | Effect |
|------|--------|
| `<!-- @suppress -->` | silence everything about the next element |
| `<!-- @suppress rule-name -->` | silence findings of that rule |
| `<!-- @suppress text -->` | silence findings whose message contains `text` |
| `<!-- @suppress-file … -->` | the same, to the end of the file |

Put the directive above the element, with or without a blank line between
them. Several directives in a row apply together, which is how one element is
excused from two different rules.

Scope: a directive reaches its own element (or file) only — a pattern in
chapter 1 will not silence the same finding in chapter 5. An empty pattern
silences everything about the element.

### A rule name, or the message text

**Write the rule name.** It does not change when the wording of a message
does, and it is listed in the tables below:

```markdown
<!-- @suppress unknown-reference -->
```

A pattern that matches no rule name is compared against the message instead,
as a case-insensitive substring. That is handy for a one-off
(`<!-- @suppress [рис:k] -->` silences just that reference) but ties the
document to today's phrasing. Rule names and message text cannot be confused
for each other, so both forms work side by side.

Every finding shows its rule in `--json` (the `rule` field).

### What happens to a silenced finding

It does not vanish: it is counted in the report footer (`· 4 suppressed`),
kept in `--json` with `"suppressed": true`, and a suppressed error does not
stop the build — that is the point of asking.

A directive that covers nothing is itself a warning: a misspelled rule name,
or a finding that has since been fixed, would otherwise look like an excuse
that still applies.

```
▲ 04-chapter1.md:12  @suppress caption-ordr matched nothing; it is not a rule
                     name, so it was matched as message text
```

## Do not

- Do not hard-code object numbers in cross-references; use `[prefix:key]`.
- Do not use the comma citation form `[1, 2]`.
- Do not rely on bold/italic for structure.
- Do not put periods after numbered chapter numbers in `#` headings.

## Related docs

- [Check rules](../rules/README.en.md) — the catalogue of check rules
- [README.en.md](../../README.en.md)
- [Limitations](../limitations/README.en.md)
