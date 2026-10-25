# Accessibility

The kit is a command-line tool, so accessibility here means its terminal output and its
documentation.

## What we aim for

- Output that makes sense as plain text: results are spelled out (`PASS`, `FAIL`, `APPROVED`,
  `CHANGES REQUESTED`), never shown only by color.
- Output that works with screen readers and when color is disabled. Rich respects the
  `NO_COLOR` environment variable.
- Documentation with real headings, alt text for images and text alternatives to
  diagrams.

## Known limitations

- The live progress display redraws in place, which some screen readers announce poorly.
  Piping the output (for example `agentkit run "..." | cat`) turns the live display off.
- The Mermaid diagram in the README has a text description in the table above it, but
  no alt text of its own.

## Reporting a barrier

Open an issue using the bug report template and mention the assistive technology you
use. Accessibility problems are treated as bugs.
