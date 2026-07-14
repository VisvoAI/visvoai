"""session_state — SessionStateMixin: "what's true about this session right now?"

Cross-turn truths (running agents, pending trust approvals) and the surfaces
that display them (footer chips, warning pop-ups, the auto side panel). These
are SESSION concerns, not turn concerns — true between turns, at startup, and
across every screen — so they live as shared helpers with reach: the app's
timers, the turn worker's post-turn hook, and any future surface (a /status
screen, headless warnings) all call the same methods. Split out of app.py in
the C-split so the frame stays a frame.
"""
from __future__ import annotations


class SessionStateMixin:
    def _sync_agent_panel(self) -> None:
        """Show the live-agent side panel while dispatches run and the terminal
        is wide enough for a split; collapse it otherwise. /runs is the full
        view — this is ambient visibility, never at the cost of the chat."""
        from visvoai.cli.widgets.agent_panel import MIN_APP_WIDTH, AgentPanel
        try:
            panel = self.query_one(AgentPanel)
        except Exception:
            return   # teardown / tests without the main screen
        count = self._agent_runs.running_count()
        want = count > 0 and self.size.width >= MIN_APP_WIDTH
        if want != panel.has_class("visible"):
            panel.set_class(want, "visible")
        sb = self._status_bar()
        if sb is not None:
            sb.set_agents(count)

    def _pending_trust(self) -> set[str]:
        """'kind:name' keys for every project agent AND skill awaiting trust."""
        out: set[str] = set()
        try:
            from visvoai.cli.agents import untrusted_agents
            out |= {f"agent:{s.name}" for s in untrusted_agents(self._cwd)}
        except Exception:
            pass   # a broken defs dir must never break startup/turn teardown
        try:
            from visvoai.cli.skills import untrusted_skills
            out |= {f"skill:{s.name}" for s in untrusted_skills(self._cwd)}
        except Exception:
            pass
        return out

    def _notify_pending_agents(self, before: set[str] | None = None) -> None:
        """Deterministic surfacing of project agents/skills awaiting trust — the
        SYSTEM's job, never the model's (it forgets). Called at startup
        (before=None: anything pending) and after each turn (before=snapshot:
        only NEW ones, so a deliberately-ignored pending item doesn't nag)."""
        fresh = self._pending_trust()
        if before is not None:
            fresh -= before
        for kind, screen in (("agent", "/agents"), ("skill", "/skills")):
            names = sorted(k.split(":", 1)[1] for k in fresh if k.startswith(kind))
            if names:
                joined = ", ".join(f"'{n}'" for n in names)
                self.notify(f"{kind.title()} {joined} needs one-time approval "
                            f"before the AI can use it — open {screen}.",
                            severity="warning", timeout=12)

