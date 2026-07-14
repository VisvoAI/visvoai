SQL / migration extras:
- Migrations reversible (a real downgrade), never edit an applied migration.
- New columns: nullable or defaulted — no table rewrite locks on big tables.
- Indexes for every new query pattern; EXPLAIN anything with a JOIN.
