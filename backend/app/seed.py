from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session
from .db import Customer, DayClose, Expense, Inventory, Product, Sale, SessionLocal

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

# Pharmacy brand mappings for realistic product grouping and multi-brand comparisons
PHARMACY_BRANDS = {
    1: ("Metformin 500mg", "Glyciphage - Franco"),
    2: ("Amlodipine 5mg", "Amlong - Micro Labs"),
    3: ("Telmisartan 40mg", "Telma - Glenmark"),
    4: ("Atorvastatin 10mg", "Atorva - Zydus"),
    5: ("Losartan 50mg", "Losacar - Zydus"),
    6: ("Glimepiride 2mg", "Amaryl - Sanofi"),
    7: ("Levothyroxine 50mcg", "Thyronorm - Abbott"),
    8: ("Pantoprazole 40mg", "Pan 40 - Alkem"),
    9: ("Clopidogrel 75mg", "Clopilet - Sun Pharma"),
    10: ("Amoxicillin-Clav 625", "Augmentin - GSK"),
    11: ("Azithromycin 500mg", "Azithral - Alembic"),
    12: ("Cefixime 200mg", "Taxim-O - Alkem"),
    13: ("Doxycycline 100mg", "Doxicip - Cipla"),
    14: ("Ofloxacin-Ornidazole", "O2 - Medley"),
    15: ("Cetirizine 10mg", "Medora"),
    16: ("Montelukast-Levocetirizine", "Montair-LC - Cipla"),
    17: ("ORS Sachet", "Electral - FDC"),
    18: ("Paracetamol 650mg", "Dolo 650 - Micro Labs"),
    19: ("Cough Syrup", "Benadryl - J&J"),
    20: ("Digene Gel", "Digene - Abbott"),
    21: ("Pain Relief Gel", "Volini - Sun Pharma"),
    22: ("Vapour Balm", "Vicks - P&G"),
    23: ("Throat Lozenges", "Strepsils - Reckitt"),
    24: ("Nasal Decongestant Drops", "Otrivin - Haleon"),
    25: ("Antacid Tablets", "Eno - Haleon"),
}


def load_demo_data(db: Session) -> bool:
    """Load CSVs from backend/data/ into the database if the products table is empty.

    Returns False if data already exists (to signal 409 Conflict).
    """
    if db.query(Product).first() is not None:
        return False

    frames = {}
    for filename, required_cols in REQUIRED_COLUMNS.items():
        file_path = DATA_DIR / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Missing required CSV file: {filename} at {file_path}")

        df = pd.read_csv(file_path)
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"{filename} is missing required columns: {missing_cols}")
        frames[filename] = df

    # Parse date columns
    frames["sales.csv"]["sale_date"] = pd.to_datetime(frames["sales.csv"]["sale_date"]).dt.date
    frames["expenses.csv"]["expense_date"] = pd.to_datetime(frames["expenses.csv"]["expense_date"]).dt.date

    # 1. Products
    prod_df = frames["products.csv"].rename(columns={"product_id": "id"})
    products_to_insert = []
    for _, r in prod_df.iterrows():
        p_id = int(r["id"])
        group_info = PHARMACY_BRANDS.get(p_id)
        if group_info:
            p_group, p_mfr = group_info
        else:
            p_group = str(r["name"]).split(" (")[0].strip()
            p_mfr = "Standard Labs"

        products_to_insert.append(
            Product(
                id=p_id,
                name=r["name"],
                category=r["category"],
                unit_cost=float(r["unit_cost"]),
                unit_price=float(r["unit_price"]),
                product_group=p_group,
                manufacturer=p_mfr,
            )
        )

    # Add competing brand for Cetirizine 10mg: Curalife (Product ID 52)
    # Medora (Product 15) vs Curalife (Product 52) in "Cetirizine 10mg" group
    curalife_prod = Product(
        id=52,
        name="Cetirizine 10mg (Curalife)",
        category="Antibiotics & Acute (Rx)",
        unit_cost=18.0,
        unit_price=24.0,
        product_group="Cetirizine 10mg",
        manufacturer="Curalife",
    )
    products_to_insert.append(curalife_prod)

    # Add competing brand for Paracetamol 650mg: Calpol (Product ID 53)
    calpol_prod = Product(
        id=53,
        name="Calpol 650mg (15 tabs)",
        category="OTC Cold & Pain",
        unit_cost=23.0,
        unit_price=30.0,
        product_group="Paracetamol 650mg",
        manufacturer="GSK",
    )
    products_to_insert.append(calpol_prod)

    # Add competing brand for Metformin 500mg: Glycomet (Product ID 54)
    glycomet_prod = Product(
        id=54,
        name="Glycomet 500mg (10 tabs)",
        category="Chronic Care (Rx)",
        unit_cost=28.0,
        unit_price=36.0,
        product_group="Metformin 500mg",
        manufacturer="USV",
    )
    products_to_insert.append(glycomet_prod)

    for p in products_to_insert:
        db.add(p)
    db.flush()

    # 2. Customers (assign mock phone numbers for refills demo)
    cust_df = frames["customers.csv"].rename(columns={"customer_id": "id"})
    customers_to_insert = []
    for _, r in cust_df.iterrows():
        c_id = int(r["id"])
        # Give real-looking 10-digit Indian phone numbers to non-walk-in customers
        phone = f"9820{c_id:06d}" if c_id != 1 else None
        customers_to_insert.append(
            Customer(
                id=c_id,
                name=r["name"],
                city=r["city"],
                phone=phone,
            )
        )
    for c in customers_to_insert:
        db.add(c)
    db.flush()

    # 3. Expenses
    exp_df = frames["expenses.csv"].rename(columns={"expense_id": "id"})
    exp_records = exp_df.to_dict(orient="records")
    db.bulk_insert_mappings(Expense, exp_records)

    # Add Expired Stock Write-off expenses over the last 12 months for profit leaks demo
    last_sale_date = frames["sales.csv"]["sale_date"].max()
    writeoff_expenses = []
    for m in range(12):
        exp_d = (last_sale_date - timedelta(days=m * 30)).replace(day=1)
        # One high month (spike > 2x median) around 3 months ago
        amt = 18500.0 if m == 3 else 5200.0 + (m * 250.0)
        writeoff_expenses.append(
            Expense(
                expense_date=exp_d,
                category="Expired Stock Write-off",
                amount=amt,
            )
        )
    for we in writeoff_expenses:
        db.add(we)
    db.flush()

    # 4. Sales
    sales_df = frames["sales.csv"].rename(columns={"sale_id": "id"})
    sales_df["source"] = "import"
    sales_df["sale_time"] = None
    sales_records = sales_df.to_dict(orient="records")
    db.bulk_insert_mappings(Sale, sales_records)

    # Insert a few sales for Curalife (Product 52) so Medora sells ~11x more than Curalife
    # Medora sold 1052 units in the last 90 days. 1052 / 11 = ~95 units.
    # We add 24 sales lines of 4 units each for Curalife (~96 units total)
    max_sale_id = int(sales_df["id"].max())
    extra_sales = []
    for i in range(24):
        s_date = last_sale_date - timedelta(days=(i * 3) + 2)
        extra_sales.append(
            Sale(
                id=max_sale_id + i + 1,
                invoice_id=f"DEMO-CURA-{i+1:04d}",
                sale_date=s_date,
                sale_time=datetime.combine(s_date, datetime.min.time()),
                customer_id=(i % 50) + 2,
                product_id=52,
                quantity=4,
                unit_price=24.0,
                total_amount=96.0,
                source="import",
            )
        )
    for s in extra_sales:
        db.add(s)
    db.flush()

    # 5. Inventory: Seed stock, reorder levels, and expiry dates
    # For Curalife (Product 52): exactly 53 units in stock as mentioned in the prompt!
    inventory_items = [
        Inventory(
            product_id=52,
            batch_no="CURA-B101",
            stock_on_hand=53,
            reorder_level=20,
            expiry_date=last_sale_date + timedelta(days=280),
            last_restock_date=last_sale_date - timedelta(days=30),
        ),
        Inventory(
            product_id=15,  # Medora Cetirizine
            batch_no="MED-B202",
            stock_on_hand=180,
            reorder_level=50,
            expiry_date=last_sale_date + timedelta(days=365),
            last_restock_date=last_sale_date - timedelta(days=15),
        ),
        Inventory(
            product_id=18,  # Dolo 650
            batch_no="DOLO-B303",
            stock_on_hand=400,
            reorder_level=100,
            expiry_date=last_sale_date + timedelta(days=500),
            last_restock_date=last_sale_date - timedelta(days=7),
        ),
        Inventory(
            product_id=53,  # Calpol 650
            batch_no="CAL-B404",
            stock_on_hand=35,
            reorder_level=50,  # Below reorder level -> status: reorder
            expiry_date=last_sale_date + timedelta(days=300),
            last_restock_date=last_sale_date - timedelta(days=45),
        ),
        Inventory(
            product_id=1,  # Metformin
            batch_no="MET-B505",
            stock_on_hand=250,
            reorder_level=60,
            expiry_date=last_sale_date + timedelta(days=45),  # Within 60 days -> expiring_soon!
            last_restock_date=last_sale_date - timedelta(days=20),
        ),
        Inventory(
            product_id=38,  # Nebulizer (Medical Device - low sales, high stock -> overstocked)
            batch_no="NEB-B606",
            stock_on_hand=45,
            reorder_level=5,
            expiry_date=last_sale_date + timedelta(days=900),
            last_restock_date=last_sale_date - timedelta(days=60),
        ),
        Inventory(
            product_id=39,  # Steam Inhaler
            batch_no="STM-B707",
            stock_on_hand=30,
            reorder_level=5,
            expiry_date=last_sale_date + timedelta(days=800),
            last_restock_date=last_sale_date - timedelta(days=60),
        ),
        Inventory(
            product_id=50,  # Surgical Gloves
            batch_no="GLV-B808",
            stock_on_hand=8,
            reorder_level=25,  # Low stock -> status: reorder
            expiry_date=last_sale_date + timedelta(days=600),
            last_restock_date=last_sale_date - timedelta(days=90),
        ),
    ]

    # Seed general inventory for remaining products
    for pid in range(2, 52):
        if pid in (15, 18, 1, 38, 39, 50):
            continue
        inventory_items.append(
            Inventory(
                product_id=pid,
                batch_no=f"BAT-{pid:03d}",
                stock_on_hand=60 + (pid * 2),
                reorder_level=20,
                expiry_date=last_sale_date + timedelta(days=180 + (pid * 10)),
                last_restock_date=last_sale_date - timedelta(days=20),
            )
        )

    for item in inventory_items:
        db.add(item)
    db.flush()

    # 6. Auto-close all distinct sales dates into day_closes so demo data is closed and immediately visible
    distinct_sales_dates = (
        db.query(
            Sale.sale_date,
            func.count(func.distinct(Sale.invoice_id)).label("inv_count"),
            func.sum(Sale.total_amount).label("rev_sum"),
        )
        .group_by(Sale.sale_date)
        .all()
    )

    day_closes_to_insert = [
        DayClose(
            date=d_val,
            closed_at=datetime.combine(d_val, datetime.max.time()),
            invoices=int(inv_count),
            revenue=float(rev_sum),
        )
        for d_val, inv_count, rev_sum in distinct_sales_dates
    ]
    db.bulk_save_objects(day_closes_to_insert)

    db.commit()
    return True
