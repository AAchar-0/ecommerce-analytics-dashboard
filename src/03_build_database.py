"""Step 3: load the cleaned CSV into a SQLite database, then add indexes and views.

Run it from the project root with the virtual environment active:
    python src/03_build_database.py

SQLite is a full SQL database stored in one file, so there is nothing to install.
The database file (retail.db) is ignored by Git because *.db is in .gitignore.
"""
import sqlite3                  # sqlite3 ships with Python: no pip install needed
from pathlib import Path

import pandas as pd

# ---------- 1. File locations ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLEAN_FILE = PROJECT_ROOT / "data" / "processed" / "clean_transactions.csv"
DB_FILE = PROJECT_ROOT / "data" / "processed" / "retail.db"
VIEWS_SQL = PROJECT_ROOT / "sql" / "01_views.sql"

# SQLite has no True/False type, so the flag columns are stored as 1 and 0.
FLAG_COLUMNS = ["is_cancellation", "is_product", "has_customer", "is_valid_sale"]


def load_clean(path: Path) -> pd.DataFrame:
    """Read the cleaned CSV and prepare it for the database."""
    df = pd.read_csv(
        path,
        dtype={"invoice": "string", "stock_code": "string", "description": "string",
               "country": "string",
               "invoice_date": "string",   # keep dates as ISO text: SQLite's date functions read it
               "customer_id": "Int64"},    # whole numbers, blanks allowed
    )
    for column in FLAG_COLUMNS:
        df[column] = df[column].astype(int)   # True -> 1, False -> 0
    return df


def create_indexes(conn: sqlite3.Connection) -> None:
    """Indexes work like a book's index: they make lookups and grouping much faster."""
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_date     ON transactions (invoice_date)",
        "CREATE INDEX IF NOT EXISTS idx_customer ON transactions (customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_product  ON transactions (stock_code)",
        "CREATE INDEX IF NOT EXISTS idx_country  ON transactions (country)",
        "CREATE INDEX IF NOT EXISTS idx_valid    ON transactions (is_valid_sale)",
    ]
    for statement in statements:
        conn.execute(statement)


def main() -> None:
    if not CLEAN_FILE.exists():
        raise FileNotFoundError(f"Run step 2 first. Missing: {CLEAN_FILE}")

    df = load_clean(CLEAN_FILE)
    print(f"Loaded {len(df):,} rows from the CSV. Writing to the database...")

    # Start fresh each time so the script can be re-run safely.
    if DB_FILE.exists():
        DB_FILE.unlink()

    # "with" closes the connection for us, and commits the changes if nothing failed.
    with sqlite3.connect(DB_FILE) as conn:
        # chunksize writes 50,000 rows at a time to keep memory use low.
        df.to_sql("transactions", conn, index=False, chunksize=50_000)
        create_indexes(conn)

        # executescript runs a whole file containing several SQL statements.
        conn.executescript(VIEWS_SQL.read_text(encoding="utf-8"))

        # ---------- Sanity check: SQL must agree with pandas ----------
        rows, revenue = conn.execute(
            "SELECT COUNT(*), ROUND(SUM(revenue), 2) FROM v_sales"
        ).fetchone()
        expected = int(df["is_valid_sale"].sum())
        print(f"v_sales has {rows:,} rows and revenue of {revenue:,.2f} GBP")
        if rows != expected:
            raise ValueError(f"Mismatch: SQL has {rows:,} valid sales, pandas has {expected:,}")

    print(f"Database ready: {DB_FILE}")


if __name__ == "__main__":
    main()
