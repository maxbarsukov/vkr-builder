# Security Policy

We take the security of `vkr-builder` seriously and appreciate responsible
reports from the community.

## Supported versions

Fixes land on `master`, and the latest release line receives them. Older lines
are best-effort.

| Version | Supported         |
| :------ | :---------------- |
| 0.1.x   | ✅ active support |
| < 0.1   | ❌ no support     |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.**

Use GitHub's private vulnerability reporting on the [Security tab](https://github.com/maxbarsukov/vkr-builder/security),
or contact the maintainers directly:

- [@maxbarsukov](https://github.com/maxbarsukov)
- [@HiterretiH](https://github.com/HiterretiH)

Include, at a minimum:

- A description of the issue and its impact.
- The version (release tag or commit SHA) you reproduced it on.
- Your OS, Python version and the engine in use — `vkr-builder doctor` prints
  all three.
- Steps, or a document, that demonstrate the problem.
- Any mitigation you have already identified.

## What to expect from us

| Step                          | Target time        |
| :---------------------------- | :----------------- |
| Acknowledgement of report     | within **7 days**  |
| First substantive response    | within **14 days** |
| Fix or mitigation available   | within **30 days** |
| Coordinated public disclosure | **90 days** by default, sooner if mutually agreed |

We will keep you informed, credit you in the release notes if you wish, and
agree the disclosure timeline with you.

## What this tool touches

`vkr-builder` is a local command-line tool. Knowing what it actually does makes
it easier to judge whether a finding is in scope:

- **Reads** Markdown, images and YAML config from the paths named in your
  profile. Config is parsed with `yaml.safe_load`; there is no code-execution
  path through it.
- **Writes** the DOCX and PDF at the configured output paths, plus a temporary
  merged `_bundle.md` next to your Markdown.
- **Launches** Microsoft Word (COM) or LibreOffice (headless) as a subprocess
  with an argument list — never through a shell.
- **Opens a loopback socket.** While paginating with LibreOffice the tool
  starts `soffice --accept=socket,host=127.0.0.1,port=<free port>` and speaks
  UNO to it. The port is bound to loopback and lives only for the build, but it
  is unauthenticated: on a shared machine another local user could reach it
  during that window.
- **Patches PDF bytes** in place to write document metadata, as an incremental
  update that never re-serialises the file.

There is no network service, no telemetry, no credential storage and no
auto-update.

## Out of scope

- Findings produced only by automated scanners, with no demonstrated exploit.
- Vulnerabilities in Microsoft Word or LibreOffice themselves — report those
  upstream and we will pick up the fix.
- Anything that requires the attacker to already control your machine.
- Resource exhaustion from a deliberately enormous document.
- Issues in dependencies that already have an upstream fix; report upstream and
  we will bump the version.

## Hardening recommendations

- Treat Markdown, images and config that came from someone else as untrusted
  input: they name the paths this tool reads and writes.
- Keep Word and LibreOffice patched. The builder never enables macros, but
  `--pdf-engine word` does open the document in Word.
- On a shared host, prefer `--pagination-engine word`, or build when no other
  users are logged in: the LibreOffice path opens the loopback UNO port
  described above.
