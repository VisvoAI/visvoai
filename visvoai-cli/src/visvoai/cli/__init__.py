"""
visvoai.cli — Developer tool CLI built on visvoai-core.

Eats its own cooking: the CLI is itself an agent that edits the local filesystem,
runs shell commands, reads files, and streams output to the terminal. It is the
reference implementation of what a visvoai-core extension looks like.

Entry point: visvoai.cli.main:cli  (registered as the `visvoai` console script)
"""
