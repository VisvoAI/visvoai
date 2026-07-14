---
description: Draft release notes from the git log
args:
  version: The version being released (the previous tag to diff from)
---
1. Run `git log $version..HEAD --oneline` to list the changes.
2. Group them: Features, Fixes, Internal. Drop chore/noise commits.
3. Write the notes in the house format — see format.md for the rules.
4. Save to RELEASE_NOTES.md and show me the result.
