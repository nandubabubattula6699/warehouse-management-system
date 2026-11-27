"""
Compare two `pg_dump --schema-only` files, ignoring ordering (of statements and of the columns inside
CREATE TABLE), comments, SET lines, ownership noise and the alembic_version table. Used to check a
database against the Alembic baseline before stamping.

    python scripts/compare_schema.py expected.sql actual.sql

Exit code 0 = identical, 1 = differences (printed as a diff of normalized DDL statements).
Reads only the two files; never connects to any database.
"""
import difflib
import os
import re
import sys

_SKIP_PREFIXES = ("SET ", "SELECT pg_catalog.set_config", "ALTER SCHEMA ", "CREATE SCHEMA ", "COMMENT ON SCHEMA ")


def _sort_columns(stmt: str) -> str:
    """CREATE TABLE t ( a ..., b ... ) -> columns sorted, so a column added later with ALTER TABLE
    (it sits at the end) compares equal. Splits only on top-level commas: numeric(10,2) stays whole."""
    if not stmt.startswith("CREATE TABLE ") or not stmt.endswith(")") or " ( " not in stmt:
        return stmt
    head, body = stmt.split(" ( ", 1)
    cols, depth, cur = [], 0, ""
    for ch in body[:-1]:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            cols.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cols.append(cur.strip())
    return f"{head} ( {', '.join(sorted(cols))} )"


def normalize(path: str) -> list[str]:
    with open(path, encoding="utf-8-sig") as f:
        txt = f.read()
    stmts = []
    for raw in txt.split(";\n"):
        lines = [ln for ln in raw.splitlines()
                 if ln.strip() and not ln.startswith("--") and not ln.startswith("\\")]
        s = " ".join(" ".join(lines).split())
        if not s or s.startswith(_SKIP_PREFIXES) or "alembic_version" in s:
            continue
        s = re.sub(r" OWNER TO \S+", "", s)
        if s.startswith("ALTER TABLE") and s.endswith("OWNER"):
            continue
        stmts.append(_sort_columns(s))
    return sorted(stmts)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a, b = normalize(sys.argv[1]), normalize(sys.argv[2])
    diff = list(difflib.unified_diff(a, b, os.path.basename(sys.argv[1]), os.path.basename(sys.argv[2]),
                                     lineterm="", n=0))
    if not diff:
        print(f"IDENTICAL ({len(a)} statements)")
        return 0
    print("\n".join(diff))
    return 1


if __name__ == "__main__":
    sys.exit(main())
