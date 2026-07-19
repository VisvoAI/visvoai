# Security

The CLI's security model (kernel-level shell sandboxing, trust gates for
repo-defined agents/skills/MCP servers, no project-level code execution) is a
core feature — reports that break it are the most valuable kind.

**Please do not open public issues for vulnerabilities.**
Use **GitHub's private vulnerability reporting**: on the repo, open the
**Security** tab → **Report a vulnerability**. The report is visible only to
you and the maintainers — never a public issue. Include details and
reproduction steps; you'll
get an acknowledgment within one week. Coordinated disclosure after a fix is
the default; credit given unless you prefer otherwise.

In scope, especially:
- escaping the read-only shell sandbox or the write classifier forcing silence
  instead of a prompt
- executing repo-controlled content without a trust approval
- path-guard bypasses (writes outside the working directory roots)
- secrets leaking into configs, traces, or logs
