import csv
from contextlib import nullcontext
import io
import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session
from .db import Customer, DayClose, Expense, Inventory, Product, Sale

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
REJECTED_DIR = Path(__file__).resolve().parent.parent / "data" / "rejected"
REJECTED_DIR.mkdir(parents=True, exist_ok=True)

TARGET_FIELDS = {
    "products": [
        "product_id",
        "name",
        "category",
        "unit_cost",
        "unit_price",
        "product_group",
        "manufacturer",
    ],
    "customers": ["customer_id", "name", "city", "phone"],
    "sales": [
        "sale_id",
        "invoice_id",
        "sale_date",
        "customer",
        "product",
        "quantity",
        "unit_price",
        "total_amount",
    ],
    "expenses": ["expense_id", "expense_date", "category", "amount"],
    "inventory": [
        "product",
        "batch_no",
        "stock_on_hand",
        "reorder_level",
        "expiry_date",
        "last_restock_date",
    ],
}

REQUIRED_FIELDS = {
    "products": ["name", "category", "unit_cost", "unit_price"],
    "customers": ["name"],
    "sales": [
        "invoice_id",
        "sale_date",
        "product",
        "quantity",
        "unit_price",
    ],
    "expenses": ["expense_date", "category", "amount"],
    "inventory": ["product", "stock_on_hand"],
}

ALIASES = {
    "name": [
        "name",
        "itemname",
        "productname",
        "medicine",
        "medicinename",
        "item",
        "product",
        "drug",
        "drugname",
    ],
    "product": [
        "product",
        "productname",
        "item",
        "itemname",
        "medicine",
        "medicinename",
        "drug",
        "drugname",
        "productid",
        "itemid",
    ],
    "customer": [
        "customer",
        "customername",
        "client",
        "clientname",
        "patient",
        "patientname",
        "buyer",
        "party",
        "partyname",
        "cust",
        "customerid",
    ],
    "quantity": ["quantity", "qty", "units", "count", "pcs", "volume", "qnty"],
    "invoice_id": [
        "invoiceid",
        "invoiceno",
        "billno",
        "billnumber",
        "invoicenumber",
        "invno",
        "bill",
        "invoice",
        "billid",
        "receiptno",
    ],
    "sale_date": ["saledate", "date", "billdate", "invoicedate", "txndate", "transactiondate"],
    "unit_price": ["unitprice", "price", "rate", "mrp", "sellingprice", "saleprice"],
    "total_amount": [
        "totalamount",
        "amount",
        "total",
        "netamount",
        "totalprice",
        "nettotal",
        "billtotal",
        "subtotal",
    ],
    "unit_cost": ["unitcost", "cost", "purchaseprice", "buyingprice", "costprice", "buyrate"],
    "phone": ["phone", "phonenumber", "mobile", "mobileno", "contact", "contactno", "cell", "telephone"],
    "city": ["city", "location", "town", "place", "address"],
    "category": ["category", "cat", "productcategory", "itemcategory", "type", "department"],
    "product_group": ["productgroup", "group", "generic", "genericname", "molecule", "salt", "composition"],
    "manufacturer": ["manufacturer", "mfr", "company", "mfg", "producer", "maker", "brand"],
    "batch_no": ["batchno", "batch", "batchnumber", "lot", "lotno", "lotnumber"],
    "stock_on_hand": [
        "stockonhand",
        "stock",
        "currentstock",
        "qtyinstock",
        "availableqty",
        "balanceqty",
        "inventory",
        "unitsinstock",
    ],
    "reorder_level": ["reorderlevel", "reorder", "minstock", "minlevel", "alertlevel", "safetystock"],
    "expiry_date": ["expirydate", "expiry", "expdate", "exp", "expirationdate"],
    "last_restock_date": ["lastrestockdate", "restockdate", "lastrestock", "restockedon", "receiveddate"],
    "product_id": ["productid", "itemid", "pid", "code"],
    "customer_id": ["customerid", "clientid", "cid"],
    "sale_id": ["saleid", "id", "transid", "txnid"],
    "expense_id": ["expenseid", "id"],
    "expense_date": ["expensedate", "date", "paymentdate"],
    "amount": ["amount", "expenseamount", "total", "cost", "spent"],
}


def normalize_string(val: str) -> str:
    """Normalize column header for alias matching (lowercase, stripped of punctuation)."""
    if not isinstance(val, str):
        val = str(val)
    return re.sub(r"[^a-z0-9]", "", val.lower())


def get_template_csv(dataset: str) -> str:
    """Return a header-only CSV string for the given dataset."""
    fields = TARGET_FIELDS.get(dataset)
    if not fields:
        raise ValueError(f"Unknown dataset '{dataset}'")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)
    return output.getvalue()


def parse_raw_file(filename: str, content: bytes) -> pd.DataFrame:
    """Parse uploaded file (.csv, .tsv, .txt, .xlsx, .json) into a DataFrame."""
    if len(content) > MAX_FILE_SIZE:
        raise ValueError("File exceeds maximum allowed size of 20 MB")

    ext = Path(filename).suffix.lower()

    if ext == ".json":
        try:
            records = json.loads(content.decode("utf-8"))
            if isinstance(records, dict):
                records = [records]
            df = pd.DataFrame(records)
        except Exception as e:
            raise ValueError(f"Invalid JSON file: {e}")
    elif ext in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name=0)
        except Exception as e:
            raise ValueError(f"Invalid Excel file: {e}")
    else:
        # Default text/csv/tsv delimiter auto-detection
        text_sample = content[:4096].decode("utf-8", errors="ignore")
        detected_sep = ","
        try:
            sniffer = csv.Sniffer()
            detected_sep = sniffer.sniff(text_sample, delimiters=",\t;|").delimiter
        except Exception:
            if "\t" in text_sample and text_sample.count("\t") > text_sample.count(","):
                detected_sep = "\t"
            elif ";" in text_sample and text_sample.count(";") > text_sample.count(","):
                detected_sep = ";"

        try:
            df = pd.read_csv(io.BytesIO(content), sep=detected_sep, skip_blank_lines=True)
        except Exception as e:
            raise ValueError(f"Failed to parse CSV/text file: {e}")

    # Remove entirely blank rows and clean column names
    df = df.dropna(how="all")
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
    return df


def suggest_mapping(dataset: str, columns: list[str]) -> dict[str, Optional[str]]:
    """Match target fields to source columns using normalized names and aliases."""
    targets = TARGET_FIELDS.get(dataset, [])
    mapping = {}
    normalized_sources = {col: normalize_string(col) for col in columns}

    for target in targets:
        matched_col = None
        target_norm = normalize_string(target)

        # 1. Exact normalized match
        for col, norm in normalized_sources.items():
            if norm == target_norm:
                matched_col = col
                break

        # 2. Alias match
        if not matched_col and target in ALIASES:
            for alias in ALIASES[target]:
                alias_norm = normalize_string(alias)
                for col, norm in normalized_sources.items():
                    if norm == alias_norm:
                        matched_col = col
                        break
                if matched_col:
                    break

        mapping[target] = matched_col

    return mapping


def preview_import(filename: str, content: bytes, dataset: str) -> dict[str, Any]:
    """Inspect uploaded file and generate suggested column mappings."""
    if dataset not in TARGET_FIELDS:
        raise ValueError(f"Unsupported dataset: {dataset}")

    df = parse_raw_file(filename, content)
    columns = list(df.columns)
    suggested = suggest_mapping(dataset, columns)

    req_fields = REQUIRED_FIELDS.get(dataset, [])
    missing_required = [f for f in req_fields if not suggested.get(f)]

    # First 5 sample rows as plain python dicts
    sample_df = df.head(5).copy()
    sample_rows = json.loads(sample_df.to_json(orient="records", date_format="iso"))

    return {
        "columns": columns,
        "row_count": int(len(df)),
        "sample_rows": sample_rows,
        "suggested_mapping": suggested,
        "missing_required": missing_required,
    }


def clean_currency_or_number(val: Any) -> float:
    """Strip currency symbols (₹, Rs, commas, $, etc.) and parse float."""
    if val is None or pd.isna(val):
        raise ValueError("Missing numeric value")
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    # Strip currency indicators, commas and currency words
    s = re.sub(r"[₹RsINR,\s$€£]", "", s, flags=re.IGNORECASE)
    if not s:
        raise ValueError("Missing numeric value")
    return float(s)


def clean_date(val: Any) -> date:
    """Parse date from common formats (YYYY-MM-DD, DD/MM/YYYY, Excel datetime, etc.)."""
    if val is None or pd.isna(val):
        raise ValueError("Missing date value")
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.date()
    if isinstance(val, date):
        return val

    s = str(val).strip()
    # Direct fast parse for common standard patterns
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10] if len(s) >= 10 else s, fmt).date()
        except ValueError:
            continue

    # Fallback to pandas parsing
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if not pd.isna(dt):
            return dt.date()
    except Exception:
        pass

    raise ValueError(f"Unrecognized date format: '{s}'")


def _resolve_prod(
    raw_prod: Any,
    product_by_id: dict[int, Product],
    product_by_name: dict[str, Product],
) -> Optional[Product]:
    """Resolve a product by numeric ID, exact name, or partial name match."""
    if raw_prod is None or pd.isna(raw_prod):
        return None
    # 1. Try numeric ID (int, float, or string digits)
    try:
        val_int = int(float(str(raw_prod).strip()))
        if val_int in product_by_id:
            return product_by_id[val_int]
    except (ValueError, TypeError, OverflowError):
        pass
    # 2. Try normalized name match
    prod_str = str(raw_prod).strip().lower()
    if prod_str in product_by_name:
        return product_by_name[prod_str]
    # 3. Try partial / prefix match
    for p_name, p_obj in product_by_name.items():
        if prod_str == p_name or prod_str in p_name or p_name in prod_str:
            return p_obj
    return None


def _resolve_cust(
    raw_cust: Any,
    customer_by_id: dict[int, Customer],
    customer_by_name: dict[str, Customer],
    walk_in: Customer,
) -> Customer:
    """Resolve customer by ID or name, defaulting to walk-in fallback."""
    if raw_cust is None or pd.isna(raw_cust):
        return walk_in
    cust_str = str(raw_cust).strip().lower()
    if not cust_str or cust_str in ("cash", "walk-in", "walkin", "counter", "nan", "none"):
        return walk_in
    # 1. Try numeric ID
    try:
        val_int = int(float(cust_str))
        if val_int in customer_by_id:
            return customer_by_id[val_int]
    except (ValueError, TypeError, OverflowError):
        pass
    # 2. Try name match
    if cust_str in customer_by_name:
        return customer_by_name[cust_str]
    return walk_in


def commit_import(
    db: Session,
    filename: str,
    content: bytes,
    dataset: str,
    mapping: dict[str, Optional[str]],
    mode: str = "append",
) -> dict[str, Any]:
    """Execute import validation, transformation, deduplication, and database insertion."""
    if isinstance(mapping, str):
        try:
            mapping = json.loads(mapping)
        except Exception:
            raise ValueError("Invalid JSON format for mapping parameter.")

    if dataset not in TARGET_FIELDS:
        raise ValueError(f"Unsupported dataset: {dataset}")

    # Validate that all required target fields are mapped to existing source columns
    req_fields = REQUIRED_FIELDS[dataset]
    missing = [f for f in req_fields if not mapping.get(f)]
    if missing:
        raise ValueError(f"Missing required target fields in mapping: {', '.join(missing)}")

    df = parse_raw_file(filename, content)
    total_rows = len(df)
    if total_rows == 0:
        return {"inserted": 0, "skipped_duplicates": 0, "rejected": [], "rejected_csv_url": None}

    # Verify source columns exist
    for target, source in mapping.items():
        if source and source not in df.columns:
            raise ValueError(f"Source column '{source}' not found in file")

    # Check if mock data is loaded
    is_mock = False
    p1 = db.query(Product).filter(Product.id == 1).first()
    if p1 and p1.name and "Metformin" in p1.name:
        is_mock = True

    # Mode: replace check
    if mode == "replace":
        if is_mock:
            # If mock data is loaded, replacing any dataset cleanly resets the mock database
            db.query(Sale).delete()
            db.query(DayClose).delete()
            db.query(Inventory).delete()
            db.query(Expense).delete()
            db.query(Customer).delete()
            db.query(Product).delete()
            db.flush()
        else:
            if dataset in ("products", "customers"):
                sales_count = db.query(Sale).count()
                if sales_count > 0:
                    # User confirmed replacing products/customers: clean up dependent sales & closes
                    db.query(Sale).delete()
                    db.query(DayClose).delete()
                    db.query(Inventory).delete()
                    db.flush()
            if dataset == "products":
                db.query(Product).delete()
            elif dataset == "customers":
                db.query(Customer).delete()
            elif dataset == "sales":
                db.query(Sale).delete()
            elif dataset == "expenses":
                db.query(Expense).delete()
            elif dataset == "inventory":
                db.query(Inventory).delete()
            db.flush()

    # Pre-load reference maps for fast lookups
    product_by_id: dict[int, Product] = {}
    product_by_name: dict[str, Product] = {}
    for p in db.query(Product).all():
        product_by_id[p.id] = p
        product_by_name[p.name.strip().lower()] = p

    customer_by_id: dict[int, Customer] = {}
    customer_by_name: dict[str, Customer] = {}
    for c in db.query(Customer).all():
        customer_by_id[c.id] = c
        customer_by_name[c.name.strip().lower()] = c

    # Set up walk-in customer fallback
    walk_in = customer_by_id.get(1)
    if not walk_in:
        for c in customer_by_name.values():
            if "walk-in" in c.name.lower() or "cash" in c.name.lower():
                walk_in = c
                break
    if not walk_in:
        walk_in = Customer(id=1, name="Walk-in Customer", city="Counter")
        with db.begin_nested():
            db.add(walk_in)
            db.flush()
        customer_by_id[1] = walk_in
        customer_by_name["walk-in customer"] = walk_in

    # Existing keys for deduplication
    existing_sale_ids = set()
    existing_sale_tuples = set()
    if dataset == "sales":
        for s in db.query(Sale.id, Sale.invoice_id, Sale.product_id, Sale.quantity, Sale.sale_date).all():
            existing_sale_ids.add(s[0])
            existing_sale_tuples.add((str(s[1]).strip().lower(), s[2], s[3], s[4]))

    existing_expense_ids = set()
    existing_expenses = set()
    if dataset == "expenses":
        for e in db.query(Expense.id, Expense.expense_date, Expense.category, Expense.amount).all():
            existing_expense_ids.add(e[0])
            existing_expenses.add((e[1], str(e[2]).strip().lower(), round(float(e[3]), 2)))

    inserted = 0
    skipped_duplicates = 0
    rejected: list[dict[str, Any]] = []
    rejected_rows_raw: list[dict[str, Any]] = []

    # Process rows
    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-indexed Excel/CSV row number (header is row 1)
        row_dict = row.to_dict()

        try:
            with (db.begin_nested() if dataset in ("products", "customers") else nullcontext()):
                if dataset == "products":
                    name = str(row_dict.get(mapping.get("name")) or "").strip()
                    if not name:
                        raise ValueError("Product name is required")

                    name_key = name.lower()
                    if mode == "append" and name_key in product_by_name:
                        skipped_duplicates += 1
                        continue

                    category = str(row_dict.get(mapping.get("category")) or "").strip()
                    if not category:
                        raise ValueError("Category is required")

                    unit_cost = clean_currency_or_number(row_dict.get(mapping.get("unit_cost")))
                    unit_price = clean_currency_or_number(row_dict.get(mapping.get("unit_price")))
                    if unit_cost < 0 or unit_price < 0:
                        raise ValueError("Prices must be non-negative")

                    prod_id = None
                    if mapping.get("product_id") and not pd.isna(row_dict.get(mapping.get("product_id"))):
                        try:
                            prod_id = int(float(str(row_dict.get(mapping.get("product_id"))).strip()))
                        except Exception:
                            pass

                    # Prevent primary key conflict
                    if prod_id is not None:
                        if prod_id in product_by_id:
                            existing_p = product_by_id[prod_id]
                            if existing_p.name.strip().lower() == name_key:
                                skipped_duplicates += 1
                                continue
                            # Different product already uses this ID: let DB auto-assign
                            prod_id = None
                        elif name_key in product_by_name:
                            skipped_duplicates += 1
                            continue

                    product_group = None
                    if mapping.get("product_group") and not pd.isna(row_dict.get(mapping.get("product_group"))):
                        product_group = str(row_dict.get(mapping.get("product_group"))).strip() or None

                    manufacturer = None
                    if mapping.get("manufacturer") and not pd.isna(row_dict.get(mapping.get("manufacturer"))):
                        manufacturer = str(row_dict.get(mapping.get("manufacturer"))).strip() or None

                    new_prod = Product(
                        id=prod_id,
                        name=name,
                        category=category,
                        unit_cost=unit_cost,
                        unit_price=unit_price,
                        product_group=product_group,
                        manufacturer=manufacturer,
                    )
                    db.add(new_prod)
                    db.flush()
                    product_by_id[new_prod.id] = new_prod
                    product_by_name[name_key] = new_prod
                    inserted += 1

                elif dataset == "customers":
                    name = str(row_dict.get(mapping.get("name")) or "").strip()
                    if not name:
                        raise ValueError("Customer name is required")

                    name_key = name.lower()
                    if mode == "append" and name_key in customer_by_name:
                        skipped_duplicates += 1
                        continue

                    city = None
                    if mapping.get("city") and not pd.isna(row_dict.get(mapping.get("city"))):
                        city = str(row_dict.get(mapping.get("city"))).strip() or None

                    phone = None
                    if mapping.get("phone") and not pd.isna(row_dict.get(mapping.get("phone"))):
                        phone = str(row_dict.get(mapping.get("phone"))).strip() or None

                    cust_id = None
                    if mapping.get("customer_id") and not pd.isna(row_dict.get(mapping.get("customer_id"))):
                        try:
                            cust_id = int(float(str(row_dict.get(mapping.get("customer_id"))).strip()))
                        except Exception:
                            pass

                    # Prevent primary key conflict
                    if cust_id is not None:
                        if cust_id in customer_by_id:
                            existing_c = customer_by_id[cust_id]
                            if existing_c.name.strip().lower() == name_key:
                                if city and not existing_c.city:
                                    existing_c.city = city
                                if phone and not existing_c.phone:
                                    existing_c.phone = phone
                                skipped_duplicates += 1
                                continue
                            cust_id = None
                        elif name_key in customer_by_name:
                            skipped_duplicates += 1
                            continue

                    new_cust = Customer(id=cust_id, name=name, city=city, phone=phone)
                    db.add(new_cust)
                    db.flush()
                    customer_by_id[new_cust.id] = new_cust
                    customer_by_name[name_key] = new_cust
                    inserted += 1

                elif dataset == "sales":
                    inv_id = str(row_dict.get(mapping.get("invoice_id")) or "").strip()
                    if not inv_id:
                        raise ValueError("Invoice ID is required")

                    s_date = clean_date(row_dict.get(mapping.get("sale_date")))

                    # Customer resolution (optional - defaults to Walk-in Customer)
                    cust_match = _resolve_cust(
                        row_dict.get(mapping.get("customer")) if mapping.get("customer") else None,
                        customer_by_id,
                        customer_by_name,
                        walk_in,
                    )

                    # Product resolution
                    raw_prod = row_dict.get(mapping.get("product"))
                    prod_match = _resolve_prod(raw_prod, product_by_id, product_by_name)
                    if not prod_match:
                        raise ValueError(f"Product '{raw_prod}' does not exist in database")

                    qty = clean_currency_or_number(row_dict.get(mapping.get("quantity")))
                    if qty <= 0 or not qty.is_integer():
                        raise ValueError(f"Quantity must be a positive integer, got '{qty}'")
                    qty = int(qty)

                    unit_price = clean_currency_or_number(row_dict.get(mapping.get("unit_price")))

                    # Total amount resolution: optional in mapping, calculate if not provided
                    raw_total = row_dict.get(mapping.get("total_amount")) if mapping.get("total_amount") else None
                    if raw_total is not None and not pd.isna(raw_total):
                        total_amount = clean_currency_or_number(raw_total)
                        expected_total = qty * unit_price
                        if abs(total_amount - expected_total) > 1.0:
                            raise ValueError(
                                f"Total amount (₹{total_amount:.2f}) differs from quantity x unit price (₹{expected_total:.2f}) by more than ₹1"
                            )
                    else:
                        total_amount = round(qty * unit_price, 2)

                    sale_id = None
                    if mapping.get("sale_id") and not pd.isna(row_dict.get(mapping.get("sale_id"))):
                        try:
                            sale_id = int(float(str(row_dict.get(mapping.get("sale_id"))).strip()))
                        except Exception:
                            pass

                    # Deduplication check
                    dup_key = (inv_id.lower(), prod_match.id, qty, s_date)
                    if dup_key in existing_sale_tuples:
                        skipped_duplicates += 1
                        continue

                    # If sale_id already exists in DB, do not clash - let DB assign auto-increment ID
                    if sale_id is not None and sale_id in existing_sale_ids:
                        sale_id = None

                    if sale_id is not None:
                        existing_sale_ids.add(sale_id)
                    existing_sale_tuples.add(dup_key)

                    source = "live" if mode == "live" else "import"
                    new_sale = Sale(
                        id=sale_id,
                        invoice_id=inv_id,
                        sale_date=s_date,
                        sale_time=datetime.now() if mode == "live" else None,
                        customer_id=cust_match.id,
                        product_id=prod_match.id,
                        quantity=qty,
                        unit_price=unit_price,
                        total_amount=total_amount,
                        source=source,
                    )
                    db.add(new_sale)
                    inserted += 1

                elif dataset == "expenses":
                    exp_date = clean_date(row_dict.get(mapping.get("expense_date")))
                    category = str(row_dict.get(mapping.get("category")) or "").strip()
                    if not category:
                        raise ValueError("Expense category is required")

                    amount = clean_currency_or_number(row_dict.get(mapping.get("amount")))
                    if amount < 0:
                        raise ValueError("Expense amount must be positive")

                    # Deduplication check
                    exp_key = (exp_date, category.lower(), round(amount, 2))
                    if exp_key in existing_expenses:
                        skipped_duplicates += 1
                        continue
                    existing_expenses.add(exp_key)

                    expense_id = None
                    if mapping.get("expense_id") and not pd.isna(row_dict.get(mapping.get("expense_id"))):
                        try:
                            expense_id = int(float(str(row_dict.get(mapping.get("expense_id"))).strip()))
                        except Exception:
                            pass

                    if expense_id is not None and expense_id in existing_expense_ids:
                        expense_id = None

                    if expense_id is not None:
                        existing_expense_ids.add(expense_id)

                    new_expense = Expense(
                        id=expense_id,
                        expense_date=exp_date,
                        category=category,
                        amount=amount,
                    )
                    db.add(new_expense)
                    inserted += 1

                elif dataset == "inventory":
                    raw_prod = row_dict.get(mapping.get("product"))
                    prod_match = _resolve_prod(raw_prod, product_by_id, product_by_name)
                    if not prod_match:
                        raise ValueError(f"Product '{raw_prod}' does not exist in database")

                    stock_on_hand = clean_currency_or_number(row_dict.get(mapping.get("stock_on_hand")))
                    stock_on_hand = int(stock_on_hand)

                    batch_no = None
                    if mapping.get("batch_no") and not pd.isna(row_dict.get(mapping.get("batch_no"))):
                        batch_no = str(row_dict.get(mapping.get("batch_no"))).strip() or None

                    reorder_level = 0
                    if mapping.get("reorder_level") and not pd.isna(row_dict.get(mapping.get("reorder_level"))):
                        reorder_level = int(clean_currency_or_number(row_dict.get(mapping.get("reorder_level"))))

                    expiry_date = None
                    if mapping.get("expiry_date") and not pd.isna(row_dict.get(mapping.get("expiry_date"))):
                        expiry_date = clean_date(row_dict.get(mapping.get("expiry_date")))

                    last_restock_date = None
                    if mapping.get("last_restock_date") and not pd.isna(row_dict.get(mapping.get("last_restock_date"))):
                        last_restock_date = clean_date(row_dict.get(mapping.get("last_restock_date")))

                    # Check if batch exists for product
                    existing_batch = None
                    if batch_no:
                        existing_batch = (
                            db.query(Inventory)
                            .filter(Inventory.product_id == prod_match.id, Inventory.batch_no == batch_no)
                            .first()
                        )

                    if existing_batch:
                        existing_batch.stock_on_hand = stock_on_hand
                        if reorder_level:
                            existing_batch.reorder_level = reorder_level
                        if expiry_date:
                            existing_batch.expiry_date = expiry_date
                        if last_restock_date:
                            existing_batch.last_restock_date = last_restock_date
                    else:
                        new_inv = Inventory(
                            product_id=prod_match.id,
                            batch_no=batch_no,
                            stock_on_hand=stock_on_hand,
                            reorder_level=reorder_level,
                            expiry_date=expiry_date,
                            last_restock_date=last_restock_date,
                        )
                        db.add(new_inv)

                    inserted += 1

        except Exception as e:
            err_msg = str(e)
            rejected.append({"row_number": row_num, "reason": err_msg})
            row_dict["reason"] = err_msg
            rejected_rows_raw.append(row_dict)

    try:
        # Auto-close sales dates for append and replace modes
        if dataset == "sales" and mode in ("append", "replace") and inserted > 0:
            db.flush()
            # Find distinct dates in sales that do not exist in day_closes
            distinct_dates = (
                db.query(Sale.sale_date)
                .filter(Sale.source == "import")
                .distinct()
                .all()
            )
            existing_closed = set(d[0] for d in db.query(DayClose.date).all())
            for (d_val,) in distinct_dates:
                if d_val not in existing_closed:
                    # Calculate invoices and revenue for that date
                    inv_count = (
                        db.query(func.count(func.distinct(Sale.invoice_id)))
                        .filter(Sale.sale_date == d_val)
                        .scalar()
                        or 0
                    )
                    rev_sum = (
                        db.query(func.sum(Sale.total_amount))
                        .filter(Sale.sale_date == d_val)
                        .scalar()
                        or 0.0
                    )
                    db.add(
                        DayClose(
                            date=d_val,
                            closed_at=datetime.now(),
                            invoices=inv_count,
                            revenue=float(rev_sum),
                        )
                    )

        db.commit()
    except Exception as e:
        db.rollback()
        raise e

    # Save rejected rows to downloadable CSV if any exist
    rejected_csv_url = None
    if rejected_rows_raw:
        file_id = f"rejected_{uuid.uuid4().hex[:10]}.csv"
        out_path = REJECTED_DIR / file_id
        rej_df = pd.DataFrame(rejected_rows_raw)
        rej_df.to_csv(out_path, index=False)
        rejected_csv_url = f"/api/import/rejected/{file_id}"

    return {
        "inserted": inserted,
        "skipped_duplicates": skipped_duplicates,
        "rejected": rejected,
        "rejected_csv_url": rejected_csv_url,
    }
