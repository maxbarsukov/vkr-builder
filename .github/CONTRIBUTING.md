# Contributing

Hey! We're glad you're thinking about contributing to **vkr-builder**. This
guide covers the development setup, the tests you're expected to run before
opening a PR, the conventions this codebase actually follows, and the handful
of couplings that are easy to miss — a new check has to be registered in two
places, and the built document is expected to be byte-for-byte reproducible.

---

## Development environment <a name="dev-env"></a>

You'll need:

- **Python 3.10+** — the floor is enforced by `doctor` and by the wrapper
  scripts. CI runs 3.10, 3.11 and 3.12.
- **A layout engine**, for anything that touches pagination, the table of
  contents or PDF export:
  - **LibreOffice** on any platform, *plus the UNO bridge*. On Debian and
    Ubuntu the bridge is a separate package: `sudo apt install python3-uno`.
  - or **Microsoft Word** with `pywin32`, Windows only.
- **qpdf**, optional, to validate the PDF the metadata writer produces.

```bash
git clone https://github.com/maxbarsukov/vkr-builder.git
cd vkr-builder

python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt # runtime deps plus pytest and watchdog
```

Check what the tool found on your machine:

```bash
python main.py doctor
```

It prints your OS, your Python version and every engine it located. Paste that
output into any bug report.

## Running the test suite <a name="testing"></a>

```bash
python -m pytest src/tests
```

The suite builds real `.docx` files and reads them back, so it needs no
network and no fixtures beyond the repository. Some tests opt out on their own:

| Skipped when | Turn it on with |
|--------------|-----------------|
| PDF conversion, unless asked for | `VKR_TEST_PDF=1` and LibreOffice installed |
| PDF structure checks, without qpdf | install `qpdf` |
| Anything driving Word | run it on Windows with Word installed |

Use `-rs` to see what skipped and why:

```bash
python -m pytest src/tests -q -rs
```

CI ([tests.yml](workflows/tests.yml)) runs the suite on Python 3.10–3.12 with
`libreoffice-writer`, `python3-uno` and `qpdf` installed, so the checks that
skip on a bare machine do run there. It then lints and builds the bundled
example and keeps the resulting DOCX and PDF as artifacts. There is no Windows
runner, so Word-specific changes need a manual pass on Windows — say so in the
PR.

## The bundled example is a fixture <a name="example"></a>

`example/` is a complete thesis *about this tool*, and it does three jobs at
once: it demonstrates every feature, it documents them, and the test suite and
CI build it. Which means:

- **If you change rendering, build it and look at the result.** A change that
  passes the unit tests can still make the document wrong.
- **If you add a markup construct, add it to the example.** Appendix В carries
  a table of every construct and how it is rendered; a construct missing from
  that table is undocumented.
- `example/VKR-example.docx` and `.pdf` are committed. Rebuild and commit them
  whenever the example's Markdown changes, so the repository never ships an
  artifact that disagrees with its source.

```bash
python main.py lint
python main.py build --pagination-engine libreoffice --pdf --pdf-engine libreoffice
```

## Reproducible output <a name="reproducible"></a>

Building the same sources twice must produce byte-identical files. Timestamps
come from `metadata.modified` in the config (falling back to
`config.NEUTRAL_TIMESTAMP`), ZIP entry times are normalised, and the PDF writer
neutralises the dates and identifiers the engines put in the Info dictionary
and the XMP packets.

This is easy to break by accident — a `datetime.now()`, an unsorted `set`, a
temporary path leaking into the output. Check it:

```bash
python main.py build --pdf && md5sum example/VKR-example.*
python main.py build --pdf && md5sum example/VKR-example.*
```

The two runs must print the same hashes.

## Code style <a name="style"></a>

Match the surrounding code. A few rules that are specific to this project:

- **Output strings are English.** Findings, log lines and progress text — all
  of them, even though the documents produced are Russian.
- **Never hardcode an output symbol.** `✓`, `→`, `·` and the rest come from
  `ui.Symbols`, which has a matching ASCII set for `--ascii` and `VKR_ASCII=1`.
  A literal glyph breaks terminals that asked for plain output.

## Adding a check or a warning <a name="findings"></a>

A new rule lives in more than one file, and missing the second one fails
quietly:

1. Raise it — `src/vkr/md_lint.py` for Markdown checks,
   `log.warning(..., extra={"rule": "..."})` for build-time ones,
   `src/vkr/diagnostics.py` for checks against a finished DOCX.
2. **Register the name in `src/vkr/suppress.py`**, under the stage that raises
   it in `_BY_STAGE`. Skip this and `<!-- @suppress your-rule -->` silently
   falls back to substring matching, and the "did you mean" hint offers the
   wrong name.
3. Document it in `docs/rules/README.md` **and** `docs/rules/README.en.md`.
4. Add the rule to `.claude/skills/vkr-findings/SKILL.md` and
   `.cursor/rules/vkr-findings.mdc`, so the assistants that read this
   repository can explain the finding they just caused.

Decide the severity deliberately: an error stops the build, a warning does
not, and `lint.strict: true` promotes every warning to an error. If a finding
can be intentional, it must be suppressible; if suppressing it would silently
damage the document, say so in the rule's documentation.

## Documentation that moves with the code <a name="docs"></a>

| What changed | What to update |
|--------------|----------------|
| CLI behaviour, a flag, a config key | `docs/cli/README.md` + `.en` |
| Markdown syntax | `docs/llm-format/README.md` + `.en`, and the example |
| A check or a warning | `docs/rules/README.md` + `.en`, `.claude/skills/`, `.cursor/rules/` |
| Something the tool deliberately does not do | `docs/limitations/README.md` + `.en` |

## Pull-request workflow <a name="prs"></a>

1. Fork the repository, or branch if you have push access.
2. Make the change, with tests where behaviour changes.
3. Run the suite, then lint and build the example. If you touched anything
   that reaches the document, check the hashes twice as above.
4. Update the documentation in both languages.
5. Open a PR against `master`. The template asks for a summary and a test plan.
6. CI runs on every push and must be green before merge.
7. If the change needs Word, say which parts you could not verify.

## What kinds of contributions are welcome? <a name="welcome"></a>

- **Bug reports** with the output of `doctor` and, ideally, the Markdown that
  reproduces the problem.
- **Formatting bugs** — a document that disagrees with GOST 7.32-2017 or with
  the ITMO requirements. Say which clause, and attach the built file.
- **New checks** for mistakes the linter lets through today.
- **Documentation** — corrections, missing examples, and translation drift
  between the Russian and English versions.
- **Adaptations for other universities.** The formatting is ITMO's reading of
  GOST; if yours differs, a config key beats a fork.
- **Feature work** — open an issue first to discuss it, unless the change is
  small and self-contained.

Not sure whether something fits? Start a thread in [GitHub Discussions](https://github.com/maxbarsukov/vkr-builder/discussions).
