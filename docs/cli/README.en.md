# Command-line reference

| en :gb: | ru :ru: |
| ---- | ---- |
| README.en.md | [README.md](README.md) |

Commands, flags, environment variables, exit codes, the report format and the
config. Getting started and the overview are in the [root README](../../README.en.md).

---

## ⌨️ Commands <a name="commands"></a>

| Command    | Purpose |
|------------|---------|
| `help`     | Help: the list of commands, `help <command>` for one of them |
| `build`    | Merge the Markdown and build the DOCX (the default) |
| `merge`    | Only merge the Markdown into a bundle |
| `docx`     | Build the DOCX from a ready bundle |
| `pdf`      | Convert a DOCX to PDF |
| `validate` | Check the config and that the input files are there |
| `lint`     | Check the Markdown for authoring mistakes |
| `stats`    | Statistics: chapters, figures, sources, size estimate |
| `preview`  | Build a single `.md` into `preview.docx` (no table of contents) |
| `diagnose` | Quality report on an already built DOCX |
| `watch`    | Rebuild when Markdown, images or listings change (with `--pdf` — the PDF too) |
| `doctor`   | Check the Python dependencies and the engines |
| `init`     | Write a `config.yaml` template |
| `profiles` | List the profiles in the config |

Useful flags for `build` / `docx` (all of them are described in `help`):

- `--pagination-engine {word,libreoffice}`
- `--pdf` and `--pdf-engine {word,libreoffice}`
- `--profile NAME`
- `--no-preflight`, `--skip-merge`, `--skip-docx`

`stats` prints the number of sections, chapters, appendices, figures, tables,
sources and words, and an estimate of the page count. The `stats.min_sources`,
`stats.page_min` and `stats.page_max` thresholds in the config produce warnings
when the document falls outside them.

`preview` builds one chapter without merging and without a table of contents:

```bash
./vkr-builder.sh preview example/md/04-chapter1.md
./vkr-builder.sh preview example/md/04-chapter1.md -o /tmp/ch1.docx
```

`watch` rebuilds on changes, running the same `lint` as `build` before every
rebuild: a markup error stops the build instead of reaching the document. With
`--pdf` it exports the PDF as well. The pause after the last edit is
`watch.debounce_ms` in the config. Needs the `watchdog` package
(`pip install watchdog`).

## 🧩 Configuration <a name="configuration"></a>

`config.yaml` (on top of `config.defaults.yaml`) sets the profile and the
engines. A minimal example:

```yaml
active_profile: example

profiles:
  example:
    docx: example/VKR-example.docx
    markdown_dir: example/md
    images_dir: example/images
    listings_dir: example/listings
    markdown_files:
      - 01-abbreviations.md
      - 02-terms.md
      # ... in document order

build:
  pagination_engine: auto          # auto | word | libreoffice
  libreoffice_path: null
  pdf: false
  pdf_engine: null
  sort_dictionary_lists: false

lint:
  strict: false

stats:
  min_sources: null
  page_min: null
  page_max: null

metadata:
  title: Моя ВКР
  author: Иван Иванов
  created: 2026-01-15
```

`metadata` fields that are not set are cleared: neither the name of whoever
authored the template nor the name of any program reaches the document. Dates
are accepted as `2026-01-15` or `2026-01-15 10:30:00`, no quotes needed. The
same values reach the PDF.

Formatting lives in a separate `style` block:

```yaml
style:
  text:
    font_family: Times New Roman
    body_font_pt: 14
  page:
    margins_cm:
      left: 3.0
      right: 1.5
```

Dashes are unified by the `style.dashes` block:

```yaml
style:
  dashes:
    normalize: true      # false — keep exactly what the Markdown says
    captions: en-dash    # en-dash | em-dash — the separator in captions
    body: en-dash        # en-dash | em-dash — a dash as punctuation in the text
```

Two cases are not configurable and are always applied:

| What | To what | Example |
|------|---------|---------|
| a dash inside a word | a hyphen | `научно–технический` → `научно-технический` |
| a dash set tight between digits | an en dash, also tight | `2025-2026 гг.` → `2025–2026 гг.` |

Only the glyph changes — the spacing stays exactly as typed. So `6 - 7` is not
treated as a range: its dash follows the general `body` rule, and the linter
reports it as `spaced-range`.

The two cases universities disagree about are configurable: the caption
separator and the dash as punctuation. The default is the en dash everywhere —
the ITMO standard is set with it both in captions («Рисунок 1 – Название») and
in running text. A university that asks for the em dash only needs `em-dash`.

Every configuration key, with comments, is listed in [`config.defaults.yaml`](../../config.defaults.yaml).

## 🚩 Global flags <a name="global-flags"></a>

These apply to every command:

| Flag | Purpose |
|------|---------|
| `--config PATH` | Path to the YAML config (default: `config.yaml` in the project directory) |
| `--defaults PATH` | Path to the system config (default: `config.defaults.yaml`) |
| `--profile NAME` | Profile from the config (overrides `active_profile`) |
| `-v` / `--verbose` | Details of every step |
| `--debug` | Internal trace (Word COM, layout passes) |
| `-q` / `--quiet` | Errors only |
| `--no-color` | No colour, no line redraw |
| `--ascii` | ASCII characters only |
| `--json` | Print the report as one JSON document on stdout |

Example:

```bash
vkr-builder.bat lint --profile example
vkr-builder.bat build -q --pdf
```

## 🖥️ Command output <a name="command-output"></a>

Every command prints a report of the same shape: a header with the command and its context, a body of steps and messages, a footer with the result and the list of files produced.

```text
  vkr-builder.sh build ───────────────────────────  example · word engine

    source     example/md  10 files
    output     example/VKR-example.docx

    ✓ checks       4 checks passed                                    0.0s
    ✓ merge        10 files → _bundle.md                              0.0s
    ✓ lint         no issues                                          0.2s
    ✓ markdown     28 headings, 4 tables, 5 figures, 8 formulas       0.0s
    ▲ 04-chapter1.md:12  unknown reference [рис:k]
    ✓ layout       2 passes, 1 table break                             21s
    ✓ document     example/VKR-example.docx  94 KB                    0.0s

  ✓ build finished in 21s · 1 warning
    document   example/VKR-example.docx   94 KB
```

The running step stays on the last line with a spinner, and during layout passes a progress bar is drawn under it. Colour and the character set can also be switched with environment variables — see below.

About the messages reporting problems:

- Every one of them names a place — `file:line` in the Markdown you wrote.
- Identical messages are printed once.
- No more than ten warnings are printed, the rest are counted in the footer; `-v` prints them all. Errors are always printed.

Everything shown above goes to **stderr**, so that stdout stays clean and can be
read by a program. Only the result reaches stdout: profile names from
`profiles`, the help text from `help`, the paths of the files produced with
`-q`, and the whole report as one JSON document with `--json`.

```bash
./vkr-builder.sh profiles | grep active
```

### For scripts and CI

`-q` prints nothing but errors and the absolute paths of every file produced, on stdout:

```bash
docx=$(./vkr-builder.sh build -q)
```

`--json` replaces the whole report with one JSON document on stdout: the command
and its context, every step with its timing, messages with severity and place,
the files produced with their sizes, and the final result. The exit code is
unchanged.

```bash
./vkr-builder.sh lint --json | jq '.findings[] | "\(.location) \(.message)"'
```

## 🌍 Environment variables <a name="environment-variables"></a>

| Variable | Effect |
|----------|--------|
| `NO_COLOR` | any value turns colour off |
| `FORCE_COLOR` | keeps colour even when the output is redirected |
| `TERM=dumb` | turns colour off just like `NO_COLOR` |
| `VKR_ASCII` | switches the output to ASCII characters, like the `--ascii` flag |
| `VKR_PROJECT_ROOT` | the directory the tool looks in for `config.yaml` and `config.defaults.yaml` |

`VKR_PROJECT_ROOT` is the only way to run a build from outside the repository
directory without naming the config paths with flags.

The remaining `VKR_`-prefixed variables are internal; there is no need to set
them by hand.

## 🔢 Exit codes <a name="exit-codes"></a>

| Code | When |
|------|------|
| `0` | success; warnings do not affect the code |
| `1` | lint or build errors, no engine available, an unreadable config |
| `2` | unknown command or an invalid flag |
