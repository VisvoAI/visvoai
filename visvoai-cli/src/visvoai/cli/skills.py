"""
Skills for the CLI — reusable workflow instructions the agent loads on demand.

The platform model, mapped onto CLI conventions:

  platform                              CLI
  ────────────────────────────────      ──────────────────────────────────────
  skills/<name>/SKILL.md                ~/.visvoai/skills/<name>/SKILL.md (global)
                                        <project>/.visvoai/skills/<name>/SKILL.md
                                        (project wins on name; a flat
                                        <name>.md also works for one-file skills)
  index in the system prompt            index in the read_skill tool description
                                        (the CLI's established pattern — same as
                                        the run_agent roster)
  read_skill_file tool                  read_skill(skill, args, resource)
  no skill runner                       same: the model follows the loaded
                                        instructions with its OWN tools — a
                                        skill grants knowledge, never capability
                                        (mutations still hit the approve() gate)

A SKILL.md: frontmatter between --- lines — `description:` (required, the index
line), optional `args:` block (named `$placeholders` the caller fills), then the
BODY = the instructions. Supporting files live next to SKILL.md and are read
lazily via read_skill(resource=...) only when the body references them —
progressive disclosure, nothing loaded speculatively.

Substitution: `$name` placeholders and `$ARGUMENTS` (all args as `k: v` lines)
are replaced when the main body is read. Supporting files are static — never
substituted.

Trust — same threat model as project agents: a repo-controlled skill body is a
prompt that steers tool use on this machine, so project-defined skills need
one-time approval (hash of the WHOLE definition in
`~/.visvoai/projects/<pid>/skill_trust.toml`; any edit re-prompts). Global
skills are implicitly trusted (the user wrote them).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_LINE_CAP = 800          # max lines returned per read (body or resource)
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

# Resource files the tool will serve (text only — this is instruction material).
_TEXT_EXTENSIONS = {".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
                    ".txt", ".sh", ".toml", ".css", ".html", ".xml"}


@dataclass(frozen=True)
class SkillSpec:
    name: str
    source: str                        # "global" | "project"
    description: str
    body: str                          # the instructions (frontmatter stripped)
    args: dict = field(default_factory=dict)   # arg name → description
    directory: Path | None = None      # None for flat single-file skills
    path: Path | None = None           # the SKILL.md / <name>.md itself

    def spec_hash(self) -> str:
        """Hash of the executable surface. The body IS the surface (it steers
        tool use), so it's all included. Resource files are hashed by NAME
        only: their content is inert until the body references it, and any
        body change that adds a reference re-prompts anyway."""
        resources = sorted(self.resource_names())
        surface = {"description": self.description, "body": self.body,
                   "args": dict(sorted(self.args.items())), "resources": resources}
        return hashlib.sha256(json.dumps(surface, sort_keys=True).encode()).hexdigest()[:16]

    def resource_names(self) -> list[str]:
        if self.directory is None or not self.directory.is_dir():
            return []
        out = []
        for f in sorted(self.directory.rglob("*")):
            if (f.is_file() and f.suffix.lower() in _TEXT_EXTENSIONS
                    and f.name.lower() != "skill.md"):
                out.append(str(f.relative_to(self.directory)))
        return out


# ── Parsing / loading ─────────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, dict, str]:
    """(meta, args, body). Frontmatter is the same simple `key: value` format
    agents use, plus a nested `args:` block of `  name: description` lines."""
    meta: dict[str, str] = {}
    args: dict[str, str] = {}
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        body = text[m.end():]
        lines = m.group(1).splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip() == "args:":
                i += 1
                while i < len(lines) and lines[i].startswith("  "):
                    if ":" in lines[i]:
                        k, v = lines[i].strip().split(":", 1)
                        args[k.strip()] = v.strip().strip("\"'")
                    i += 1
                continue
            if ":" in line and not line.lstrip().startswith("#"):
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
            i += 1
    return meta, args, body.strip()


def _parse_skill(path: Path, directory: Path | None, source: str) -> SkillSpec | None:
    """One definition file → SkillSpec, or None (logged) if malformed."""
    name = (directory.name if directory is not None else path.stem)
    if not _NAME_RE.match(name):
        logger.warning("skills: invalid skill name '%s' (%s) — skipped", name, path)
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("skills: unreadable %s: %s", path, e)
        return None
    meta, args, body = _parse_frontmatter(text)
    if not body:
        logger.warning("skills: %s has an empty body — skipped", path)
        return None
    return SkillSpec(
        name=name, source=source,
        description=meta.get("description", "").strip() or f"skill '{name}'",
        body=body, args=args, directory=directory, path=path,
    )


def _skills_dir_global() -> Path:
    from visvoai.cli.store import visvoai_home
    return visvoai_home() / "skills"


def _skills_dir_project(cwd: str) -> Path:
    from visvoai.cli.store import project_root
    try:
        return project_root(cwd) / ".visvoai" / "skills"
    except Exception:
        return Path(cwd) / ".visvoai" / "skills"


def _load_dir(root: Path, source: str) -> dict[str, SkillSpec]:
    """A skills root: each child is either `<name>/SKILL.md` (directory skill,
    may carry resources) or a flat `<name>.md` (one-file skill)."""
    if not root.is_dir():
        return {}
    out: dict[str, SkillSpec] = {}
    for child in sorted(root.iterdir()):
        spec = None
        if child.is_dir():
            entry = next((child / n for n in ("SKILL.md", "skill.md")
                          if (child / n).is_file()), None)
            if entry is None:
                logger.warning("skills: %s has no SKILL.md — skipped", child)
                continue
            spec = _parse_skill(entry, child, source)
        elif child.suffix == ".md":
            spec = _parse_skill(child, None, source)
        if spec:
            out[spec.name] = spec
    return out


def _extra_dirs(config_path: Path, base: Path) -> list[Path]:
    """`[skills] extra_dirs = [...]` from one config file — external skill
    folders (another CLI's ~/.claude/skills, a repo's skills/ tree, shared
    dotfiles) so one library serves every tool. Relative entries resolve
    against the config file's project root; `~` expands."""
    if not config_path.exists():
        return []
    try:
        data = tomllib.loads(config_path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("skills: unreadable config %s: %s", config_path, e)
        return []
    dirs = (data.get("skills") or {}).get("extra_dirs") or []
    out: list[Path] = []
    for d in dirs:
        if not isinstance(d, str):
            continue
        p = Path(d).expanduser()
        out.append(p if p.is_absolute() else (base / p).resolve())
    return out


def _store(cwd: str) -> "LayeredSpecStore":
    """Layer order (later wins): global dir → global extra_dirs (list order) →
    project dir → project extra_dirs. TRUST FOLLOWS THE DECLARING CONFIG, not
    the dir's location: a dir listed in ~/.visvoai/config.toml is user-chosen
    ("global", implicitly trusted); one listed in the project's config is
    repo-controlled ("project", one-time approval) — who controls the BYTES
    decides the tier. Coincident-layer dedupe is the store's job."""
    from visvoai.cli.keys import global_config_path
    from visvoai.cli.specstore import Layer, LayeredSpecStore
    from visvoai.cli.store import project_root

    def dir_layer(d: Path, tier: str) -> Layer:
        return Layer(source=tier, trusted=(tier == "global"), identity=d,
                     load=lambda d=d, t=tier: _load_dir(d, t))

    home = _skills_dir_global().parent
    layers = [dir_layer(_skills_dir_global(), "global")]
    layers += [dir_layer(d, "global")
               for d in _extra_dirs(global_config_path(), home)]
    layers.append(dir_layer(_skills_dir_project(cwd), "project"))
    try:
        proot = project_root(cwd)
    except Exception:
        proot = Path(cwd)
    proj_cfg = proot / ".visvoai" / "config.toml"
    if proj_cfg.resolve() != global_config_path().resolve():
        layers += [dir_layer(d, "project") for d in _extra_dirs(proj_cfg, proot)]
    return LayeredSpecStore("skill", cwd, layers)


def load_skill_specs(cwd: str) -> dict[str, SkillSpec]:
    """Merged roster — see _store() for layering and trust tiers."""
    return _store(cwd).load()


# ── Trust (generic mechanics live in specstore; kind="skill") ────────────────

def is_trusted(cwd: str, spec: SkillSpec) -> bool:
    return _store(cwd).is_trusted(spec)


def trust_skill(cwd: str, spec: SkillSpec) -> None:
    _store(cwd).trust(spec)


def untrusted_skills(cwd: str) -> list[SkillSpec]:
    return _store(cwd).untrusted()


# ── Substitution ──────────────────────────────────────────────────────────────

def substitute_args(body: str, declared: dict, given: dict | None) -> str:
    """Replace $name placeholders with given values; undeclared placeholders
    are left alone (they may be shell syntax inside the instructions).
    $ARGUMENTS expands to all given args as `name: value` lines."""
    given = given or {}
    if "$ARGUMENTS" in body:
        block = "\n".join(f"{k}: {v}" for k, v in given.items()) or "(none)"
        body = body.replace("$ARGUMENTS", block)

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key in given:
            return str(given[key])
        if key in declared:
            return ""            # declared but not given → empty, like the platform
        return m.group(0)        # not a skill arg — leave untouched

    return _PLACEHOLDER_RE.sub(sub, body)


# ── Definition writing (`visvoai skills create`) ─────────────────────────────

SKILL_TEMPLATE = """\
---
description: {description}
{args_block}---

{body}
"""


def write_skill_file(root: Path, name: str, *, description: str,
                     args: dict | None, body: str) -> Path:
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid skill name '{name}' (use letters/digits/-/_)")
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    args_block = ""
    if args:
        args_block = "args:\n" + "".join(f"  {k}: {v}\n" for k, v in args.items())
    path.write_text(SKILL_TEMPLATE.format(description=description,
                                          args_block=args_block, body=body),
                    encoding="utf-8")
    return path


# ── The read_skill tool ───────────────────────────────────────────────────────

def _index_description(specs: dict[str, SkillSpec]) -> str:
    lines = [
        "Load a SKILL — reusable step-by-step instructions for a known workflow "
        "— then FOLLOW those instructions with your own tools. Read a skill "
        "BEFORE improvising whenever the user's request matches one below.",
        "This tool is the ONLY way to load a skill: never search the filesystem "
        "for skill files (a repo's own skills/ folders are NOT this roster) — "
        "one call by name replaces all of that and fills in the arguments.",
        "",
        "Available skills:",
    ]
    for s in specs.values():
        arg_note = ""
        if s.args:
            arg_note = "  (args: " + ", ".join(f"${a}" for a in s.args) + ")"
        lines.append(f"- {s.name}: {s.description}{arg_note}")
    if len(specs) == 0:
        lines.append("- (none defined yet)")
    lines += [
        "",
        "Call with the skill name exactly as listed; pass `args` for the $named "
        "placeholders. If the loaded instructions reference a supporting file, "
        "read it with `resource` set to that exact path — only when needed, "
        "never speculatively.",
        "To CREATE a new skill (when asked to): write "
        ".visvoai/skills/<name>/SKILL.md (this project) or "
        "~/.visvoai/skills/<name>/SKILL.md (all projects) — frontmatter with "
        "`description:` (one line; this index shows it) and an optional `args:` "
        "block of `  name: description` lines; the BODY is the instructions "
        "($name placeholders where args go). Supporting reference files go next "
        "to SKILL.md; tell the reader when to load which. It appears here next "
        "turn (project skills first need one-time approval in /skills — tell "
        "the user). A skill is INSTRUCTIONS, not capability — don't create one "
        "when the user wants an agent (a delegated worker with its own tools).",
    ]
    return "\n".join(lines)


def build_read_skill_tool(cwd: str):
    """The `read_skill(skill, args, resource)` tool bound to this session's
    roster. Rebuilt every turn so file edits are picked up live; untrusted
    project skills are excluded until approved in /skills. Read-only — never
    gated, safe for every agent tier."""
    from langchain_core.tools import StructuredTool

    from visvoai.cli.tools import cap_lines

    specs = {n: s for n, s in load_skill_specs(cwd).items() if is_trusted(cwd, s)}

    async def _read_skill(skill: str, args: dict | None = None,
                          resource: str | None = None) -> str:
        spec = specs.get(skill)
        if spec is None:
            known = ", ".join(specs) or "(none)"
            return f"ERROR: unknown skill '{skill}'. Available: {known}"
        if resource:
            if spec.directory is None:
                return (f"ERROR: skill '{skill}' is a single file — it has no "
                        "supporting resources.")
            if resource not in spec.resource_names():
                have = ", ".join(spec.resource_names()) or "(none)"
                return (f"ERROR: no resource '{resource}' in skill '{skill}'. "
                        f"Available: {have}")
            try:
                content = (spec.directory / resource).read_text(encoding="utf-8")
            except OSError as e:
                return f"ERROR: {e}"
            return cap_lines(content, SKILL_LINE_CAP)
        body = substitute_args(spec.body, spec.args, args)
        header = f"# Skill: {spec.name}\n\n"
        if spec.resource_names():
            header += ("Supporting files (load via resource= ONLY when the "
                       "instructions below call for them): "
                       + ", ".join(spec.resource_names()) + "\n\n")
        return cap_lines(header + body, SKILL_LINE_CAP)

    return StructuredTool.from_function(
        coroutine=_read_skill,
        name="read_skill",
        description=_index_description(specs),
    )
