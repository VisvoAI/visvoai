"""StyleRaceGuard — survive Textual's mount/compositor race on TextArea.

A timer-driven compositor refresh can paint a freshly-mounted TextArea
subclass BEFORE its `_component_styles` registry is populated from CSS; the
paint then queries `get_component_rich_style("text-area--gutter")` and
Textual raises KeyError from inside its own timer callback — crashing the
whole app over one unpainted frame (upstream: Textualize/textual#6208,
closed as not-planned; load-dependent, so CI runners hit it while dev
machines rarely do).

The guard returns a blank style for exactly that window: one frame renders
its gutter unstyled (we hide gutters anyway), the next frame — CSS applied —
is normal. Mix into every TextArea subclass in this package.
"""
from __future__ import annotations

from rich.style import Style


class StyleRaceGuard:
    def get_component_rich_style(self, *names: str, partial: bool = False) -> Style:
        try:
            return super().get_component_rich_style(*names, partial=partial)
        except KeyError:
            return Style()
