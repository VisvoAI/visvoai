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
