from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session
from .db import Customer, Expense, Product, Sale, SessionLocal

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

REQUIRED_COLUMNS = {
    "products.csv": ["product_id", "name", "category", "unit_cost", "unit_price"],
    "customers.csv": ["customer_id", "name", "city"],
    "sales.csv": [
        "sale_id",
        "invoice_id",
        "sale_date",
        "customer_id",
        "product_id",
        "quantity",
        "unit_price",
        "total_amount",
    ],
    "expenses.csv": ["expense_id", "expense_date", "category", "amount"],
}


def load_csvs(db: Session) -> None:
    """Validate and bulk insert CSV data from backend/data/ into the database."""
    dataframes = {}

    # 1. Read and validate required columns for each CSV file
    for filename, required_cols in REQUIRED_COLUMNS.items():
        file_path = DATA_DIR / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Missing required CSV file: {filename} at {file_path}")

        df = pd.read_csv(file_path)
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"{filename} is missing required columns: {missing_cols}")

        dataframes[filename] = df

    # 2. Parse date columns to real Python date objects
    dataframes["sales.csv"]["sale_date"] = pd.to_datetime(dataframes["sales.csv"]["sale_date"]).dt.date
    dataframes["expenses.csv"]["expense_date"] = pd.to_datetime(dataframes["expenses.csv"]["expense_date"]).dt.date

    # 3. Rename *_id to id and bulk insert in dependency order
    mappings = [
        ("products.csv", "product_id", Product),
        ("customers.csv", "customer_id", Customer),
        ("sales.csv", "sale_id", Sale),
        ("expenses.csv", "expense_id", Expense),
    ]

    for filename, id_col, model in mappings:
        df = dataframes[filename].rename(columns={id_col: "id"})
        records = df.to_dict(orient="records")
        db.bulk_insert_mappings(model, records)

    db.commit()


def seed_if_empty() -> None:
    """Create a session and seed CSV data only if the products table is empty."""
    db = SessionLocal()
    try:
        # Check if products table already has records; never reload if data exists
        if db.query(Product).first() is not None:
            return
        load_csvs(db)
    finally:
        db.close()

