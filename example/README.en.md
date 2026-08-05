# Demo thesis example

| en :gb: | ru :ru: |
| ---- | ---- |
| README.en.md | [README.md](README.md) |

A complete runnable example: Markdown chapters, images, and pre-built output
files. The thesis text describes this tool and demonstrates its features.

## Quick start

From the repository root (where `main.py` and `config.yaml` are):

```bash
./vkr-builder.sh build          # Linux/macOS
vkr-builder.bat build           # Windows
```

The engine picks itself: Word if it is installed, LibreOffice otherwise. With
the PDF as well:

```bash
./vkr-builder.sh build --pdf
```

The `example` profile in `config.yaml` points at this directory.

## What each file shows

| File | Worth a look for |
|------|------------------|
| `01-abbreviations.md`, `02-terms.md` | dictionary sections: one entry per line, sorted alphabetically |
| `03-introduction.md` | a structural section with its canonical heading |
| `04-chapter1.md` | a numbered chapter, subsections, lists, 2 tables, citations by key |
| `05-chapter2.md` | 3 figures with captions and references, 8 formulas, a listing pulled from a file |
| `06-conclusion.md`, `07-sources.md` | the conclusion and a source list ordered by first mention |
| `08-appendix-a.md` | three listings pulled from files |
| `09-appendix-b.md` | an appendix with figures and its own numbering, `Б.1` and `Б.2` |
| `10-appendix-c.md` | long tables: carried over with a repeated header and a «Продолжение таблицы» caption, plus a reference of markup constructs |

## Layout

| Path | Purpose |
|------|---------|
| `md/` | Chapter Markdown files merged in config order |
| `images/` | Images referenced from Markdown |
| `listings/` | Sources the chapters pull in with `@listing` |
| `VKR-example.docx` | Generated DOCX ([sample](VKR-example.docx)) |
| `VKR-example.pdf` | Generated PDF when `--pdf` is used ([sample](VKR-example.pdf)) |

The built files are committed and kept in step with the sources, so they can be
opened without building anything. During a build a merged `_bundle.md` appears
in `md/` and is removed afterwards.

## Learn more

- [The root README](../README.en.md) — installation and commands
- [Markdown format rules](../docs/llm-format/README.en.md) — Markdown conventions
- [Limitations](../docs/limitations/README.en.md) — known gaps
