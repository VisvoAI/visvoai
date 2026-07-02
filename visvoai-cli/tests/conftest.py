"""Test config — suppress benign asyncio teardown warnings.

The package is installed (editable) in the test env, so `import visvoai.cli` works
without any sys.path manipulation.
"""
import warnings

# Benign RuntimeWarnings from Textual/Pilot internal timers that may fire after the
# loop closes on teardown — not bugs in our code; our widgets' cleanup hooks handle
# the cases that matter. Don't let them fail CI.
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message=".*was never awaited.*",
)
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message=".*Task was destroyed but it is pending.*",
)


import pytest


@pytest.fixture(autouse=True)
def _isolate_visvoai_home(tmp_path, monkeypatch):
    """Every test gets a throwaway VISVOAI_HOME. Prefs/state/store writes must
    never touch the developer's real ~/.visvoai, and a pref saved by one test
    (e.g. theme persistence) must not leak into the next."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "visvoai-home"))
