## Summary

<!-- What this changes, and why. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactoring
- [ ] Tests
- [ ] Build / CI

## Test plan

<!-- What you ran and on what. CI runs Linux only: if this touches Word, COM
     or the Word PDF export, say whether you could verify it on Windows. -->

- [ ] `python -m pytest src/tests` passes
- [ ] `python main.py lint` and a build of the bundled example succeed

## Checklist

- [ ] Two consecutive builds produce identical files — or the document was
      meant to change, and `example/VKR-example.docx` / `.pdf` are rebuilt and
      committed with it
- [ ] Docs updated in **both** languages (`README.md` + `.en.md`,
      `docs/*/*.md` + `.en.md`)
- [ ] A new finding is registered in `src/vkr/suppress.py` and documented in
      `docs/rules/README.md` + `.en.md`, `.claude/skills/`, `.cursor/rules/`
- [ ] New user-visible strings are English, and symbols come from `ui.Symbols`
      rather than literal glyphs

## Related issues

<!-- Fixes #123 -->
