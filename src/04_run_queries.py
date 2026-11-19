"""Step 4: run the named queries in the sql/ folder and print the results.

Run everything:
    python src/04_run_queries.py

Run just one query by its name:
    python src/04_run_queries.py top_10_products
"""
import re                       # re = regular expressions: pattern matching for text
import sqlite3
import sys                      # sys.argv holds what you typed after the script name
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_ROOT / "data" / "processed" / "retail.db"
SQL_DIR = PROJECT_ROOT / "sql"


def split_queries(text: str) -> dict:
    """Split one SQL file into {query name: SQL text} using the '-- name:' marker lines."""
    # The pattern captures the name after "-- name:". re.split then returns:
    # [text before the first marker, name1, sql1, name2, sql2, ...]
    parts = re.split(r"^-- name:\s*(.+)$", text, flags=re.MULTILINE)
    names = parts[1::2]         # every second item starting at 1: the names
    bodies = parts[2::2]        # every second item starting at 2: the SQL
    return {name.strip(): body.strip() for name, body in zip(names, bodies)}


def load_queries() -> dict:
    """Collect the queries from sql/02_*.sql, sql/03_*.sql, and so on (not the views file)."""
    queries = {}
    # glob finds files matching a pattern; [2-9] means a digit from 2 to 9.
    for sql_file in sorted(SQL_DIR.glob("0[2-9]_*.sql")):
        queries.update(split_queries(sql_file.read_text(encoding="utf-8")))
    return queries


def main() -> None:
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Run step 3 first. Missing: {DB_FILE}")

    queries = load_queries()

    # Optional filter: sys.argv[1:] is the list of names typed after the script name.
    wanted = sys.argv[1:]
    unknown = [name for name in wanted if name not in queries]
    if unknown:
        raise SystemExit(f"Unknown query {unknown}. Available: {list(queries)}")

    with sqlite3.connect(DB_FILE) as conn:
        for name, sql in queries.items():
            if wanted and name not in wanted:
                continue
            print(f"\n===== {name} =====")
            result = pd.read_sql_query(sql, conn)    # run the SQL and get a pandas table
            print(result.to_string(index=False))     # index=False hides the row numbers


if __name__ == "__main__":
    main()
