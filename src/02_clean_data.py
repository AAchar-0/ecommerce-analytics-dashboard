"""Step 2: clean the combined data and flag rows for later analysis.

Run it from the project root with the virtual environment active:
    python src/02_clean_data.py

Design choice: we remove only exact duplicates. Everything else that looks odd
(cancellations, non-product codes, missing customers) is FLAGGED, not deleted,
so SQL queries can filter openly and the decisions stay visible.
"""
from pathlib import Path

import pandas as pd

# ---------- 1. File locations ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN_FILE = PROJECT_ROOT / "data" / "processed" / "online_retail_raw.csv"
OUT_FILE = PROJECT_ROOT / "data" / "processed" / "clean_transactions.csv"

# Original column name -> tidy snake_case name (lowercase, underscores, no spaces).
# Tidy names are easier to type and work well in SQL.
RENAME = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}


def check_columns(path: Path) -> None:
    """Stop early, with a helpful message, if a column name is not what we expect."""
    actual = list(pd.read_csv(path, nrows=0).columns)      # nrows=0 reads only the header
    missing = [name for name in RENAME if name not in actual]
    if missing:
        raise ValueError(f"Missing columns: {missing}. The file has: {actual}")


def load_raw(path: Path) -> pd.DataFrame:
    """Read the CSV from step 1 with sensible data types."""
    return pd.read_csv(
        path,
        # Keep these as text: invoices can start with a letter (C = cancellation),
        # and stock codes can be like 85123A.
        dtype={"Invoice": "string", "StockCode": "string",
               "Description": "string", "Country": "string"},
        parse_dates=["InvoiceDate"],                        # turn date text into real dates
    )


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return the cleaned table plus a dictionary of counts for the report."""
    report = {"rows_loaded": len(df)}

    df = df.rename(columns=RENAME)

    # --- Remove exact duplicates (the overlap between the two sheets) ---
    before = len(df)
    df = df.drop_duplicates()
    report["duplicates_removed"] = before - len(df)

    # --- Tidy text columns ---
    df["description"] = df["description"].str.strip()       # remove stray spaces at the ends
    df["country"] = df["country"].str.strip()
    df["stock_code"] = df["stock_code"].str.strip().str.upper()

    # --- Customer ID: whole numbers, with blanks allowed ---
    # Plain int cannot hold blanks; pandas' "Int64" (capital I) can.
    df["customer_id"] = df["customer_id"].astype("Int64")

    # --- Revenue per line (negative for cancellations and returns) ---
    df["revenue"] = (df["quantity"] * df["unit_price"]).round(2)

    # --- Flag columns: True or False for each row ---
    # Invoices starting with "C" are cancellations.
    df["is_cancellation"] = df["invoice"].str.startswith("C").fillna(False).astype(bool)
    # Real products have a 5-digit code, optionally followed by letters (e.g. 85123A).
    # Codes like POST, M, D, BANK CHARGES and ADJUST are fees or adjustments, not products.
    df["is_product"] = df["stock_code"].str.match(r"^\d{5}[A-Z]*$").fillna(False).astype(bool)
    df["has_customer"] = df["customer_id"].notna()
    # A valid sale: a real product, bought (not cancelled), with positive quantity and price.
    df["is_valid_sale"] = (
        ~df["is_cancellation"] & df["is_product"] & (df["quantity"] > 0) & (df["unit_price"] > 0)
    )

    return df.reset_index(drop=True), report


def print_report(df: pd.DataFrame, report: dict) -> None:
    """Show the numbers that describe the cleaned data."""
    sales = df[df["is_valid_sale"]]                         # keep only the valid-sale rows

    print("\n===== Cleaning report =====")
    print(f"Rows loaded:                {report['rows_loaded']:,}")
    print(f"Duplicates removed:         {report['duplicates_removed']:,}")
    print(f"Rows kept:                  {len(df):,}")
    print(f"Cancellation rows:          {df['is_cancellation'].sum():,}")
    print(f"Non-product rows:           {(~df['is_product']).sum():,}")
    print(f"Rows without a customer:    {(~df['has_customer']).sum():,}")
    print(f"Valid sale rows:            {len(sales):,}")
    print(f"Revenue from valid sales:   {sales['revenue'].sum():,.2f} GBP")
    print(f"Revenue lost to cancels:    {df.loc[df['is_cancellation'], 'revenue'].sum():,.2f} GBP")
    print(f"Customers (with an ID):     {df['customer_id'].nunique():,}")
    print(f"Products sold:              {sales['stock_code'].nunique():,}")
    print(f"Countries:                  {df['country'].nunique():,}")
    print(f"Date range:                 {df['invoice_date'].min()} to {df['invoice_date'].max()}")

    # Monthly revenue preview. resample("MS") groups by calendar month (MS = Month Start).
    monthly = sales.set_index("invoice_date")["revenue"].resample("MS").sum().round(0)
    print("\n--- Monthly revenue from valid sales (GBP) ---")
    print(monthly.to_string())


def main() -> None:
    if not IN_FILE.exists():
        raise FileNotFoundError(f"Run step 1 first. Missing: {IN_FILE}")

    check_columns(IN_FILE)
    df, report = clean(load_raw(IN_FILE))
    print_report(df, report)

    df.to_csv(OUT_FILE, index=False)
    print(f"\nSaved {len(df):,} rows to {OUT_FILE}")


if __name__ == "__main__":
    main()
