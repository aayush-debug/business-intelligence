#!/usr/bin/env python3
"""Build precomputed JSON and CSV snapshots from local database for SNAPSHOT_MODE."""

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

# Ensure backend imports resolve properly
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
SNAPSHOTS_DIR = BACKEND_DIR / "snapshots"
DB_PATH = BACKEND_DIR / "company_brain.db"

if not DB_PATH.exists():
    raise FileNotFoundError(f"Database file not found at {DB_PATH}")

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SNAPSHOT_MODE"] = "false"
sys.path.insert(0, str(BACKEND_DIR))

from app import analytics as A
from app.db import (
    Customer,
    DayClose,
    Expense,
    Inventory,
    Product,
    Sale,
    SessionLocal,
    engine,
)
from sqlalchemy import text


def get_data_status(db):
    p_cnt = db.query(Product).count()
    c_cnt = db.query(Customer).count()
    s_cnt = db.query(Sale).count()
    e_cnt = db.query(Expense).count()
    i_cnt = db.query(Inventory).count()
    first_sale = db.execute(text("SELECT MIN(sale_date) FROM sales")).scalar()
    last_sale = db.execute(text("SELECT MAX(sale_date) FROM sales")).scalar()
    last_closed = db.execute(text("SELECT MAX(date) FROM day_closes")).scalar()

    def _fmt(d):
        if d is None:
            return None
        return d.isoformat() if hasattr(d, "isoformat") else str(d)

    return {
        "products": {"rows": p_cnt, "loaded": p_cnt > 0},
        "customers": {"rows": c_cnt, "loaded": c_cnt > 0},
        "sales": {"rows": s_cnt, "loaded": s_cnt > 0},
        "expenses": {"rows": e_cnt, "loaded": e_cnt > 0},
        "inventory": {"rows": i_cnt, "loaded": i_cnt > 0},
        "first_sale_date": _fmt(first_sale),
        "last_sale_date": _fmt(last_sale),
        "last_closed_date": _fmt(last_closed),
        "is_mock_data": True,
    }


def get_stats(db):
    return {
        "products": db.query(Product).count(),
        "customers": db.query(Customer).count(),
        "sales": db.query(Sale).count(),
        "expenses": db.query(Expense).count(),
        "inventory": db.query(Inventory).count(),
        "day_closes": db.query(DayClose).count(),
    }


def get_day_status(db):
    last_closed = db.execute(text("SELECT MAX(date) FROM day_closes")).scalar()
    open_sales = db.execute(text("""
        SELECT sale_date, COUNT(DISTINCT invoice_id) AS inv_count, COUNT(id) AS line_count
        FROM sales
        WHERE sale_date NOT IN (SELECT date FROM day_closes)
        GROUP BY sale_date
        ORDER BY sale_date ASC
    """)).fetchall()

    open_days = []
    for r in open_sales:
        d = r.sale_date
        d_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
        open_days.append({
            "date": d_str,
            "invoices": int(r.inv_count),
            "lines": int(r.line_count),
        })

    return {
        "last_closed_date": last_closed.isoformat() if hasattr(last_closed, "isoformat") else str(last_closed) if last_closed else None,
        "open_days": open_days,
        "today": date.today().isoformat(),
        "is_mock_data": True,
    }


def build_snapshots():
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()

    files_written = {}

    def write_json(filename: str, data: Any):
        path = SNAPSHOTS_DIR / filename
        content = json.dumps(data, indent=2, default=str)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        size = len(content.encode("utf-8"))
        files_written[filename] = {
            "size": size,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }

    def write_text(filename: str, content: str):
        path = SNAPSHOTS_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        size = len(content.encode("utf-8"))
        files_written[filename] = {
            "size": size,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }

    print("Building snapshots from database...")

    # 1. Combinations: days in {30, 90, 365, 0}
    days_list = [30, 90, 365, 0]

    for d in days_list:
        print(f"  Computing days={d} analytics...")
        # kpis
        k_data = A.kpis(days=d)
        write_json(f"kpis__days-{d}.json", k_data)

        # top-products
        tp_data = A.top_products(days=d, limit=8)
        write_json(f"top_products__days-{d}.json", tp_data)
        write_json(f"top-products__days-{d}.json", tp_data)

        # top-customers
        tc_data = A.top_customers(days=d, limit=8)
        write_json(f"top_customers__days-{d}.json", tc_data)
        write_json(f"top-customers__days-{d}.json", tc_data)

        # categories
        cat_data = A.categories(days=d)
        write_json(f"categories__days-{d}.json", cat_data)

        # anomalies
        anom_data = A.anomalies(days=d)
        write_json(f"anomalies__days-{d}.json", anom_data)

        # brands/comparison
        bc_data = A.brands_comparison(days=d)
        write_json(f"brands_comparison__days-{d}.json", bc_data)
        write_json(f"brands-comparison__days-{d}.json", bc_data)

        # profit/leaks
        pl_data = A.profit_leaks(days=d)
        write_json(f"profit_leaks__days-{d}.json", pl_data)
        write_json(f"profit-leaks__days-{d}.json", pl_data)

        # basket/pairs
        bp_data = A.basket_pairs(days=d, min_count=20, limit=15)
        write_json(f"basket_pairs__days-{d}.json", bp_data)
        write_json(f"basket-pairs__days-{d}.json", bp_data)

    # 2. Trend for granularity in {day, week, month} x days in {30, 90, 365, 0}
    for g in ["day", "week", "month"]:
        for d in days_list:
            t_data = A.trend(granularity=g, days=d)
            write_json(f"trend__granularity-{g}__days-{d}.json", t_data)

    # 3. Forecast with horizon 30
    fc_data = A.forecast(horizon=30)
    write_json("forecast__horizon-30.json", fc_data)
    write_json("forecast.json", fc_data)

    # 4. Inventory status
    inv_data = A.inventory_status()
    write_json("inventory_status.json", inv_data)
    write_json("inventory-status.json", inv_data)

    # 5. Reorder suggestions for lead_days in {3, 5, 7, 10} x cover_days in {7, 14, 21, 30}
    for ld in [3, 5, 7, 10]:
        for cd in [7, 14, 21, 30]:
            r_data = A.reorder_suggestions(lead_days=ld, cover_days=cd)
            write_json(f"reorder_suggestions__lead_days-{ld}__cover_days-{cd}.json", r_data)

    # Default reorder export.csv (lead_days=5, cover_days=14)
    r_default = A.reorder_suggestions(lead_days=5, cover_days=14)
    csv_rows = ["manufacturer,product,qty,unit_cost,line_cost"]
    for l in r_default["lines"]:
        mfr = f'"{l["manufacturer"]}"' if "," in l["manufacturer"] else l["manufacturer"]
        prd = f'"{l["product"]}"' if "," in l["product"] else l["product"]
        csv_rows.append(f"{mfr},{prd},{l['suggested_qty']},{l['unit_cost']},{l['line_cost']}")
    reorder_csv = "\n".join(csv_rows)
    write_text("reorder_export.csv", reorder_csv)
    write_text("reorder_export__lead_days-5__cover_days-14.csv", reorder_csv)

    # 6. Day summaries (limit 14)
    ds_data = A.day_summaries(limit=14)
    write_json("day_summaries__limit-14.json", ds_data)
    write_json("day_summaries.json", ds_data)

    # 7. Day summary for each of the last 14 closed days
    last_closed_date = None
    for item in ds_data:
        d_str = item["date"]
        d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        if last_closed_date is None:
            last_closed_date = d_str
        d_summary = A.day_summary(d_obj)
        write_json(f"day_summary__date-{d_str}.json", d_summary)

    if last_closed_date:
        d_latest = A.day_summary(datetime.strptime(last_closed_date, "%Y-%m-%d").date())
        write_json("day_summary.json", d_latest)

    # 8. Data status, stats, day status
    write_json("data_status.json", get_data_status(db))
    write_json("data-status.json", get_data_status(db))
    write_json("stats.json", get_stats(db))
    write_json("day_status.json", get_day_status(db))
    write_json("day-status.json", get_day_status(db))

    # 9. Anomaly explanations for all flagged dates
    anom_all = A.anomalies(days=0)
    for flag in anom_all.get("flagged", []):
        f_date = flag["date"]
        exp_data = A.explain_anomaly(f_date)
        write_json(f"explain_anomaly__date-{f_date}.json", exp_data)

    # 10. Refills snapshot (default)
    refills_data = A.refills(within_days=5, include_names=False)
    write_json("refills__within_days-5__include_names-false.json", refills_data)
    write_json("refills.json", refills_data)

    db.close()

    # Manifest
    built_at = datetime.now(timezone.utc).isoformat()
    total_size = sum(meta["size"] for meta in files_written.values())
    manifest = {
        "snapshot_built_at": built_at,
        "store_name": "Apollo Pharmacy (Indiranagar)",
        "file_count": len(files_written),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "files": files_written,
    }

    manifest_path = SNAPSHOTS_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    total_files = len(files_written) + 1
    full_size = total_size + manifest_path.stat().st_size

    print("\n✓ Snapshot build complete!")
    print(f"Total files: {total_files}")
    print(f"Total size: {round(full_size / (1024 * 1024), 2)} MB ({full_size:,} bytes)")

    if full_size > 15 * 1024 * 1024:
        raise ValueError(f"Snapshot size {full_size} exceeds 15 MB limit!")

    return total_files, full_size


if __name__ == "__main__":
    build_snapshots()

