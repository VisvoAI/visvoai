---
description: Review a pull request or diff with house rules, sized to the change
args:
  target: What to review — a PR number, branch, or "working tree"
---
A COMPLEX skill: it classifies first, then loads only the reference file the
branch needs — the model never reads all three. This is progressive
disclosure working; copy the shape for your own multi-file workflows.

## Step 1 — Classify (no file reads yet)
Look at $target: run `git diff --stat` for it and classify the change:
Output: {size: "small" (<150 changed lines) | "large", risk: "low" | "touches
auth/db/money paths"}

## Step 2 — Load ONE rules file, per the classification
- small + low risk    → read checklist-quick.md
- large OR risky      → read checklist-deep.md
- if the diff touches SQL/migrations, ALSO read sql-rules.md (only then)

## Step 3 — Review
Read the diff hunk by hunk against the loaded checklist. For each finding:
file:line, severity (blocker/major/nit), one-line why, concrete fix.

## Step 4 — Report
Findings ordered by severity, then a verdict: approve / approve-with-nits /
request-changes. State what you did NOT review (paths, generated files).
