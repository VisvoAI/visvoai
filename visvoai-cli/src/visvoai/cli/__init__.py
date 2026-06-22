"""
visvoai.cli — Developer tool CLI built on visvoai-core.

Entry point: `visvoai "your prompt"` (registered as a console script).
The agent edits local files, runs shell commands, and streams output to stdout.

Quick start (inside the Docker backend container):
  python -m visvoai.cli.main "list the files in /app/backend/tools/"
"""
