"""Step 1: load the raw Excel file, combine its sheets, and inspect the result.

Run it from the project root with the virtual environment active:
    python src/01_load_and_inspect.py
"""
from pathlib import Path   # Path builds file locations that work on any operating system

import pandas as pd        # pandas: the standard Python library for tables of data

# ---------- 1. File locations ----------
# __file__ is this script's own path. .parent.parent climbs two levels:
# src/01_load_and_inspect.py -> src -> project root.
# Building paths from the script's location means the script works
# no matter which folder you run it from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "online_retail_II.xlsx"      # the "/" joins path parts
OUT_FILE = PROJECT_ROOT / "data" / "processed" / "online_retail_raw.csv"

# Make pandas print wider tables instead of hiding columns behind "..."
pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 20)


def load_all_sheets(path: Path) -> pd.DataFrame:
    """Read every sheet of the Excel file and stack them into one table."""
    # sheet_name=None means "read all sheets". The result is a dictionary:
    # {sheet name: table}.
    sheets = pd.read_excel(path, sheet_name=None)

    # Show what each sheet contains. .items() gives (name, table) pairs.
    for name, table in sheets.items():
        print(f"Sheet '{name}': {table.shape[0]:,} rows x {table.shape[1]} columns")

    # concat stacks tables on top of each other.
    # ignore_index=True renumbers the rows 0, 1, 2... instead of keeping each sheet's numbers.
    return pd.concat(sheets.values(), ignore_index=True)


def inspect(df: pd.DataFrame) -> None:
    """Print the checks we run on any new dataset before touching it."""
    print("\n--- Shape (rows, columns) ---")
    print(f"{df.shape[0]:,} rows, {df.shape[1]} columns")

    print("\n--- Column names and data types ---")
    print(df.dtypes)                     # dtype = what kind of values each column holds

    print("\n--- First 5 rows ---")
    print(df.head())

    print("\n--- Missing values per column ---")
    # isna() marks each empty cell True; sum() counts the Trues in each column.
    print(df.isna().sum())

    print("\n--- Exact duplicate rows ---")
    # duplicated() marks rows identical to an earlier row. The two sheets are
    # expected to overlap in December 2010, so duplicates are likely.
    print(f"{df.duplicated().sum():,} duplicated rows")

    print("\n--- Summary of numeric columns ---")
    print(df.describe())                 # count, mean, min, max and quartiles


def main() -> None:
    if not RAW_FILE.exists():
        # Stop early with a clear message instead of a confusing error.
        raise FileNotFoundError(f"Put the dataset here first: {RAW_FILE}")

    print("Reading the Excel file. This can take 1 to 3 minutes...")
    df = load_all_sheets(RAW_FILE)
    inspect(df)

    # Save a CSV copy: later scripts will load it in seconds instead of minutes.
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)   # create the folder if it is missing
    df.to_csv(OUT_FILE, index=False)                      # index=False: don't write row numbers
    print(f"\nSaved {len(df):,} rows to {OUT_FILE}")


# This line means: only run main() when the file is run directly,
# not when another script imports it.
if __name__ == "__main__":
    main()
