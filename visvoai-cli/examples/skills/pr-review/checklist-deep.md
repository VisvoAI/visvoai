Deep pass (large or risky changes):
- Trace every changed public surface to its callers — anything broken silently?
- Error paths: what happens when the network/db call fails mid-way?
- Concurrency: shared state touched without the existing lock/pattern?
- Migration/rollout: can old and new code coexist during deploy?
- Security: input validation at trust boundaries, secrets never logged.
