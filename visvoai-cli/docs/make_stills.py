"""Generate the README/website SVG stills — deterministic, one command:

    .venv/bin/python docs/make_stills.py

Each scene stages real widgets with the demo/mock machinery (no network, no
keys) and exports Textual's native SVG — pixel-perfect, ~50KB, regenerable
whenever the UI changes. Scenes are chosen to show one differentiator each.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

DOCS = Path(__file__).parent
sys.path.insert(0, str(DOCS.parent / "src"))

# Neutral stage: run from a scratch project dir (no real paths in the footer)
# and suppress the what's-new panel (it re-arms on every version bump).
_stage = tempfile.mkdtemp(prefix="acme-web-")
os.chdir(_stage)

from visvoai.cli import VisvoApp as _VisvoApp  # noqa: E402


class VisvoApp(_VisvoApp):
    def _maybe_mount_changelog_panel(self) -> None:
        pass


async def scene_agents_split() -> None:
    """The money shot: conversation left, two live agents right, chip + gauge."""
    app = VisvoApp()
    async with app.run_test(size=(160, 44)) as pilot:
        await pilot.pause()
        from textual.containers import VerticalScroll

        from visvoai.cli.widgets import Assistant, UserMsg

        log = app.query_one("#log", VerticalScroll)
        await app._mount_block(log, UserMsg(
            "audit the app: performance in both themes, and find unused CSS"), "user")
        a = Assistant()
        await app._mount_block(log, a, "answer")
        await a.add("I'll run this in parallel — the **performance-validator** agent "
                    "audits both themes while an **explore** agent sweeps for unused "
                    "CSS variables.")
        n1 = await app._tool_node(log, "run_agent",
                                  "performance-validator — audit light & dark themes")
        n1.set_status("running")
        n2 = await app._tool_node(log, "run_agent",
                                  "explore — find unused CSS variables in src/styles")
        n2.set_status("running")

        reg = app._agent_runs
        reg.register("c1", "performance-validator", "audit light & dark themes")
        reg.step_start("c1", "s1", "run_shell", "yarn build")
        reg.step_end("c1", "s1", "compiled in 2.0s", ok=True)
        reg.step_start("c1", "s2", "start_process", "node .next/standalone/server.js")
        reg.step_end("c1", "s2", "started p1 (pid 38843)", ok=True)
        reg.step_start("c1", "s3", "run_shell", "npx lighthouse http://localhost:3004 …")
        reg.register("c2", "explore", "find unused CSS variables")
        reg.step_start("c2", "t1", "run_shell", 'rg -n "--[a-z-]+:" src/styles')
        reg.step_end("c2", "t1", "47 declarations in 6 files", ok=True)
        reg.step_start("c2", "t2", "read_file", "src/styles/tokens.css")

        app._sync_agent_panel()
        from visvoai.cli.widgets.agent_panel import AgentPanel
        panel = app.query_one(AgentPanel)
        panel._tick()
        for _ in range(6):
            await pilot.pause()
        for pane in panel.query("_RunPane"):
            pane.tick()
        await pilot.pause()
        app.query_one("#status").set_context(14, 3600)
        app.query_one("#status").set_cost(0.0112)
        await pilot.pause()
        app.save_screenshot(str(DOCS / "still_agents_split.svg"))


async def scene_runs() -> None:
    """/runs — full-width list + selected run's ToolRow log."""
    app = VisvoApp()
    async with app.run_test(size=(160, 44)) as pilot:
        await pilot.pause()
        reg = app._agent_runs
        reg.register("c1", "performance-validator", "audit light & dark themes with Lighthouse")
        for i, (tool, target, out) in enumerate([
            ("run_shell", "yarn build", "compiled in 2.0s"),
            ("start_process", "node .next/standalone/server.js", "started p1"),
            ("run_shell", "curl -I http://localhost:3004", "HTTP/1.1 200 OK"),
            ("run_shell", "npx lighthouse http://localhost:3004 --output json", "report written"),
        ]):
            reg.step_start("c1", f"s{i}", tool, target)
            reg.step_end("c1", f"s{i}", out, ok=True)
        reg.step_start("c1", "s9", "run_shell", "npx lighthouse (dark theme) …")
        reg.register("c2", "explore", "find unused CSS variables")
        reg.step_start("c2", "t1", "run_shell", 'rg -n "--[a-z-]+:" src/styles')
        reg.step_end("c2", "t1", "47 declarations in 6 files", ok=True)
        reg.finish("c2", ok=True,
                   summary="[agent: explore · 2 tool calls · 4.1k tokens · $0.0011 · 9s]",
                   final="3 unused variables: --text-ghost, --rail-dim, --old-accent.")

        from visvoai.cli.screens import AgentRunsScreen
        app.push_screen(AgentRunsScreen(reg))
        for _ in range(6):
            await pilot.pause()
        app.save_screenshot(str(DOCS / "still_runs.svg"))


async def scene_trust() -> None:
    """/skills — a project-defined skill awaiting one-time approval."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        proj = Path(td) / "repo"
        d = proj / ".visvoai" / "skills" / "deploy-runbook"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\ndescription: Deploy to staging with our checks\n---\n"
            "1. Run the smoke tests…\n")
        g = Path(td) / "home-skills"
        for name, desc in [("release-notes", "Draft release notes from the git log"),
                           ("pr-review", "Review a PR with house rules, sized to the change")]:
            sd = g / name
            sd.mkdir(parents=True)
            (sd / "SKILL.md").write_text(f"---\ndescription: {desc}\n---\nSteps…\n")

        from visvoai.cli import skills as sk
        specs = {}
        specs.update(sk._load_dir(g, "global"))
        specs.update(sk._load_dir(proj / ".visvoai" / "skills", "project"))
        trusted = {n: (s.source == "global") for n, s in specs.items()}

        app = VisvoApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            from visvoai.cli.screens import SkillsScreen
            app.push_screen(SkillsScreen(list(specs.values()), trusted))
            for _ in range(4):
                await pilot.pause()
            app.save_screenshot(str(DOCS / "still_trust.svg"))


async def scene_approval() -> None:
    """The permission gate: an edit approval with its diff, warning rail visible."""
    app = VisvoApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        from textual.containers import VerticalScroll

        from visvoai.cli.widgets import CleanDiff, Selection, UserMsg

        log = app.query_one("#log", VerticalScroll)
        await app._mount_block(log, UserMsg("rate-limit the /items endpoint"), "user")
        node = await app._tool_node(log, "edit_file", "api/middleware/limiter.py")
        from visvoai.cli.mock import MIDDLEWARE_FIX_DIFF
        await node.set_body(CleanDiff("api/middleware/limiter.py",
                                      MIDDLEWARE_FIX_DIFF), collapsed=False)
        node.set_rail("+3 −1")
        node.set_status("running")
        sel = Selection("Do you want to make this edit to limiter.py?",
                        ["Yes   (recommended)", "Yes (allow all this session)", "No"])
        await app._mount_block(log, sel, "hitl")
        for _ in range(4):
            await pilot.pause()
        app.save_screenshot(str(DOCS / "still_approval.svg"))


async def scene_model_picker() -> None:
    """/model — the live registry: pricing, thinking, connected state."""
    app = VisvoApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.run_worker(app._model_picker_flow())
        for _ in range(8):
            await pilot.pause()
        from visvoai.cli.screens import ModelScreen
        if app.query(ModelScreen):
            app.save_screenshot(str(DOCS / "still_model.svg"))


def _svg_to_png() -> None:
    """READMEs use PNG: GitHub's image proxy blocks the SVGs' CDN @font-face
    (blank cells). rsvg needs Fira Code installed (brew install font-fira-code)
    and xml:space (it ignores the stylesheet's white-space: pre)."""
    import shutil
    import subprocess
    if not shutil.which("rsvg-convert"):
        print("! rsvg-convert missing (brew install librsvg) — PNGs not refreshed")
        return
    for f in sorted(DOCS.glob("still_*.svg")):
        patched = f.read_text().replace("<text ", '<text xml:space="preserve" ')
        tmp = f.with_suffix(".tmp.svg")
        tmp.write_text(patched)
        subprocess.run(["rsvg-convert", "-w", "1600", str(tmp),
                        "-o", str(f.with_suffix(".png"))], check=True)
        tmp.unlink()
        print(f"✓ {f.with_suffix('.png').name}")


async def main() -> None:
    for scene in (scene_agents_split, scene_runs, scene_trust,
                  scene_approval, scene_model_picker):
        try:
            await scene()
            print(f"✓ {scene.__name__}")
        except Exception as e:
            print(f"✗ {scene.__name__}: {e}")
    _svg_to_png()


if __name__ == "__main__":
    asyncio.run(main())
