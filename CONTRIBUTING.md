# Contributing

Thanks for helping improve the Multi-Agent Starter Kit. Bug reports, fixes, docs and new
agent ideas are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on the
  approach.
- Security problems go through [SECURITY.md](SECURITY.md), never a public issue.
- By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

The tests run offline with no API key: a scripted stand-in replaces the LLM.

## Pull requests

1. Branch from `main` and keep each PR to one change.
2. Add or update a test for any behavior you change, and make sure `pytest` passes.
3. Update the README when you change configuration, the CLI or the graph.
4. Never commit `.env` or an API key.
5. Fill in the pull request template; CI must pass before review.
