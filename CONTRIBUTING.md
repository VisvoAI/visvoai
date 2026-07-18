# Contributing

Thanks for looking under the hood. Ground rules first, because this repo has
one unusual property worth knowing before you open a PR.

## How this repo is maintained

This is the public half of an open-core monorepo. It is synced (one-way) from
a private repository whose CI runs the same guards you see here. **PRs are
welcome and reviewed here** — when accepted, a maintainer applies your commits
to the source monorepo (authorship preserved via `git am`/cherry-pick) and the
next sync publishes them back out. Your commit lands with your name on it;
there may be a short delay between merge and appearance.

## Conduct

Participation is governed by our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Sign-off (DCO)

Commits must carry a `Signed-off-by:` line (`git commit -s`) certifying the
[Developer Certificate of Origin](https://developercertificate.org/) — you
wrote the change or have the right to submit it under MIT. This is the
lightweight alternative to a CLA and keeps future licensing options clean.

## Development setup

Each package is self-contained (uv or plain pip):

```bash
cd visvoai-cli          # or visvoai-core / visvoai-ai
uv venv
uv pip install -e ../visvoai-ai -e ../visvoai-core -e ".[dev]"
uv run pytest -q
```

## House rules

- **Tests pass, always** — CI runs every package's suite on each PR.
- **Behavior changes come with tests**; pure refactors must not edit existing
  tests (that's the proof they're pure).
- **Comments explain *why*, never *what*** — no filler comments.
- Each package's `AGENTS.md` describes its conventions — read the one for the
  area you're touching; update it if you change the module's shape.
- Versioning: `0.MINOR.PATCH` per package, only the package that changed,
  with a CHANGELOG entry (visvoai-cli additionally mirrors its changelog to
  `src/visvoai/cli/assets/` — a test enforces the sync).

## Scope guidance

Good first contributions: provider integrations (`visvoai-ai`), CLI tools and
widgets, docs/examples, test coverage. For anything architectural (new seams,
new subsystems), open an issue first — the extension-seam design is deliberate
and we'd rather align before you write code.
