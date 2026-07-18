# docs — media assets, regenerable

Nothing here is hand-made; everything regenerates in one command, so it can't
drift from the UI:

| Asset | Regenerate with |
|---|---|
| `hero.gif` — the README recording (real model, unscripted agent behavior; only the keystrokes are staged) | `vhs hero.tape` (stage a small demo repo first — see the tape's header comment) |
| `still_*.svg` — the gallery (real widgets, no network/keys) | `../.venv/bin/python make_stills.py` |
