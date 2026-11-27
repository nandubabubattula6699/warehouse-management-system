# Prime directive: ACCURACY - when speed and accuracy conflict, accuracy wins.

1. Inventory changes only through recorded movements (who/when/what/qty/from/to/
   reason). Never update a quantity silently. Never delete history.
2. Manual adjustments need a reason; large ones need supervisor approval.
3. Scan-verify physical steps where possible (receive, putaway, pick, pack).
4. Documents must balance before closing; mismatches go to a human, never
   auto-accept.
5. AI-read data is validated and never invented; unclear = ask/flag.
6. DB constraints enforce correctness; all schema changes via Alembic only.
7. Allbirds (Part 1, Lines) data is never changed by migrations or cleanups
   unless I explicitly say so.
8. Never touch production or Railway without my explicit OK in that message.
