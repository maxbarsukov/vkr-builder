---
name: vkr-building
description: Run vkr-builder — build the DOCX or PDF, preview one chapter, check the environment, watch for changes, or read its report and JSON output. Use when asked to build, rebuild, export, run doctor/validate/stats, or when interpreting what a run printed.
---

# Running the build

Call the launcher, not `main.py` — it finds Python and names itself in the
tool's own hints:

```bash
vkr-builder.bat build          # Windows
./vkr-builder.sh build         # Linux/macOS
python main.py build           # only if the launchers cannot be used
```

`build` is the default command, so bare `vkr-builder.bat` builds too.

## Commands

| Command | What it does |
|---------|--------------|
| `build` | merge → lint → document (+ `--pdf`) |
| `merge` | only produce the bundle |
| `docx` | build from an existing bundle |
| `pdf [docx]` | convert a DOCX to PDF |
| `preview <file.md>` | build one file, no TOC, next to the source |
| `lint` / `stats` / `validate` | checks and numbers, no document |
| `diagnose <docx>` | quality report on a finished document |
| `watch` | rebuild on change (needs `watchdog`) |
| `doctor` | what is installed and which engine would be used |
| `init` / `profiles` / `help` | config template, profile list, usage |

Useful flags: `--profile NAME`, `--pdf`, `--pagination-engine {auto,word,libreoffice}`,
`--skip-merge`, `--skip-docx`, `--no-preflight`, `--diagnose`.

## Engines

`pagination_engine: auto` is the default: Word if it is installed (more
accurate for GOST layout), otherwise LibreOffice. The header says which one
was chosen — `word engine (auto)`. Run `doctor` before blaming a build:

```
    ✓ word         Word 16
    ✓ libreoffice  /usr/bin/soffice
    ✓ pagination   auto → word · Word 16
```

A missing engine is a warning there (one of the two is enough); "no layout
engine available" is a command failure.

## Reading the report

```
    ✓ lint         no issues                                          0.2s
    ▲ 10-appendix-c.md:13  unknown reference [рис:k]
    ⠹ layout       pass 2/3 · fitting tables                          6.9s
      46%          ━━━━━━━━━━━━━━───────────────────    3/8 tables
  ✓ build finished in 23s · 1 warning
    document   example/VKR-example.docx   94 KB
```

- Steps carry facts and timings; the footer carries the outcome, the counts
  and the files produced.
- Findings name the **source** file and line, not the merged bundle.
- `· N suppressed` means an `@suppress` directive silenced something on
  purpose. Do not report a run as clean if that number is non-zero.
- Verbosity: `-v` adds per-step notes, `--debug` adds the Word/LibreOffice
  trace, `-q` prints errors only.

## Machine-readable output

```bash
docx=$(./vkr-builder.sh build -q)        # stdout: absolute paths produced
./vkr-builder.sh lint --json | jq '.findings[]'
```

`--json` prints the whole report as one document on stdout: command,
context, steps with timings, findings (severity, message, location, rule,
suppressed), artifacts with sizes, result. Exit codes are unchanged:
**0** success, **1** the command failed, **2** the command line was wrong.

## Docker

```bash
docker build -t vkr-builder .
docker run --rm -v "$PWD/example:/work/example" vkr-builder build --pdf
```

The image has no Word, so `auto` resolves to LibreOffice; mount a volume
over `example/` to collect the result.

## Do not

- Do not edit `_bundle.md` — it is generated and deleted every run.
- Do not hand-edit generated DOCX or PDF; rebuild it.
- Do not add `--no-preflight` to silence lint errors; fix the markdown.
- Do not report success from a run whose footer says `✗` or whose exit code
  is non-zero, even if a DOCX was written.
