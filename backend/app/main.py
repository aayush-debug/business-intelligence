from contextlib import asynccontextmanager
from datetime import date, datetime
import logging
import os
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from . import analytics as A
from .analytics import Granularity
from . import chat as C
from . import snapshots as S
from .snapshots import is_snapshot_mode
from .db import (
    Base,
    Customer,
    DayClose,
    Expense,
    Inventory,
    Product,
    Sale,
    SessionLocal,
    engine,
    get_db,
)
from . import importer as imp
from . import reports as R
from . import email_digest as ED
from .seed import load_demo_data

logger = logging.getLogger("companybrain")

STORE_TZ = os.getenv("STORE_TZ", "Asia/Kolkata")
CRON_SECRET = os.getenv("CRON_SECRET", "cron_secret_123")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup creates database tables only when NOT running in snapshot mode
    if not is_snapshot_mode():
        Base.metadata.create_all(bind=engine)
        auto_seed = os.getenv("AUTO_SEED", "false").lower() in ("true", "1", "yes")
        if auto_seed:
            try:
                db = SessionLocal()
                load_demo_data(db)
                db.close()
            except Exception as e:
                logger.warning(f"Auto-seed check/load skipped: {e}")
    yield


app = FastAPI(title="Company Brain", lifespan=lifespan)

# CORS configuration
raw_origins = os.getenv("FRONTEND_ORIGIN")
if raw_origins is None or not raw_origins.strip():
    origins = ["*"]
else:
    origins = [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True if "*" not in origins else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Health & Database Status
# ---------------------------------------------------------

@app.get("/ping")
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    """Return platform runtime configuration and snapshot demo metadata."""
    if is_snapshot_mode():
        manifest = S.get_manifest()
        return {
            "demo_mode": True,
            "snapshot_mode": True,
            "store_name": manifest.get("store_name", "Apollo Pharmacy (Indiranagar)"),
            "snapshot_built_at": manifest.get("snapshot_built_at"),
        }
    return {
        "demo_mode": False,
        "snapshot_mode": False,
        "store_name": "Company Brain",
        "snapshot_built_at": None,
    }


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    """Return row counts for database tables."""
    if is_snapshot_mode():
        data = S.get_snapshot("stats.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return {
        "products": db.query(Product).count(),
        "customers": db.query(Customer).count(),
        "sales": db.query(Sale).count(),
        "expenses": db.query(Expense).count(),
        "inventory": db.query(Inventory).count(),
        "day_closes": db.query(DayClose).count(),
    }


@app.get("/api/data/status")
def data_status(db: Session = Depends(get_db)):
    """Return dataset loading status and sales/closed date boundaries."""
    if is_snapshot_mode():
        data = S.get_snapshot("data_status.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")

    p_cnt = db.query(Product).count()
    c_cnt = db.query(Customer).count()
    s_cnt = db.query(Sale).count()
    e_cnt = db.query(Expense).count()
    i_cnt = db.query(Inventory).count()

    first_sale = db.execute(text("SELECT MIN(sale_date) FROM sales")).scalar()
    last_sale = db.execute(text("SELECT MAX(sale_date) FROM sales")).scalar()
    last_closed = db.execute(text("SELECT MAX(date) FROM day_closes")).scalar()

    is_mock = False
    if p_cnt > 0:
        p1 = db.query(Product).filter(Product.id == 1).first()
        if p1 and p1.name and "Metformin" in p1.name:
            is_mock = True

    def _fmt(d):
        if d is None:
            return None
        if isinstance(d, str):
            return d
        return d.isoformat()

    return {
        "products": {"rows": p_cnt, "loaded": p_cnt > 0},
        "customers": {"rows": c_cnt, "loaded": c_cnt > 0},
        "sales": {"rows": s_cnt, "loaded": s_cnt > 0},
        "expenses": {"rows": e_cnt, "loaded": e_cnt > 0},
        "inventory": {"rows": i_cnt, "loaded": i_cnt > 0},
        "first_sale_date": _fmt(first_sale),
        "last_sale_date": _fmt(last_sale),
        "last_closed_date": _fmt(last_closed),
        "is_mock_data": is_mock,
    }


@app.post("/api/demo/load")
def demo_load(force: bool = False, db: Session = Depends(get_db)):
    """Load sample CSV dataset. Pass force=true to clear existing data and reload."""
    if is_snapshot_mode():
        raise HTTPException(status_code=403, detail="Write operations are disabled in demo mode.")
    if force:
        db.query(Sale).delete()
        db.query(DayClose).delete()
        db.query(Inventory).delete()
        db.query(Expense).delete()
        db.query(Customer).delete()
        db.query(Product).delete()
        db.commit()
        A.clear_cache()
    success = load_demo_data(db)
    if not success:
        raise HTTPException(
            status_code=409,
            detail="Demo data can only be loaded when the database is empty. Pass force=true to reload."
        )
    A.clear_cache()
    return {"status": "ok", "message": "Demo data loaded successfully."}


@app.post("/api/data/reset")
def reset_data(db: Session = Depends(get_db)):
    """Reset all tables to an empty database state so user can upload their own data."""
    if is_snapshot_mode():
        raise HTTPException(status_code=403, detail="Write operations are disabled in demo mode.")
    db.query(Sale).delete()
    db.query(DayClose).delete()
    db.query(Inventory).delete()
    db.query(Expense).delete()
    db.query(Customer).delete()
    db.query(Product).delete()
    db.commit()
    A.clear_cache()
    return {"status": "ok", "message": "Database cleared. You can now upload your own business data."}


# ---------------------------------------------------------
# Data Import Endpoints
# ---------------------------------------------------------

@app.get("/api/import/template/{dataset}")
def import_template(dataset: str):
    """Return a header-only CSV template for the dataset."""
    csv_content = imp.get_template_csv(dataset)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={dataset}_template.csv"},
    )


@app.post("/api/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    dataset: str = Form(...),
):
    """Parse file and return column mappings and preview rows."""
    content = await file.read()
    filename = file.filename or "uploaded_file"
    return imp.preview_import(filename, content, dataset)


@app.post("/api/import/commit")
async def import_commit(
    file: UploadFile = File(...),
    dataset: str = Form(...),
    mapping: str = Form(...),
    mode: str = Form("append"),
    db: Session = Depends(get_db),
):
    """Validate, clean, and insert rows in a single atomic transaction."""
    if is_snapshot_mode():
        raise HTTPException(status_code=403, detail="Write operations are disabled in demo mode.")
    content = await file.read()
    filename = file.filename or "uploaded_file"
    try:
        res = imp.commit_import(db, filename, content, dataset, mapping, mode)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    A.clear_cache()
    return res


@app.get("/api/import/rejected/{filename}")
def import_rejected(filename: str):
    """Download CSV file of rejected rows with explanation reasons."""
    from fastapi.responses import FileResponse
    safe_name = os.path.basename(filename)
    file_path = imp.REJECTED_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Rejected rows file not found")
    return FileResponse(
        path=file_path,
        media_type="text/csv",
        filename=safe_name,
    )


# ---------------------------------------------------------
# Core Analytics Endpoints
# ---------------------------------------------------------

@app.get("/api/kpis")
def kpis(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Return key performance indicators for the specified window."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"kpis__days-{norm_days}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.kpis(days=days)


@app.get("/api/trend")
def trend(
    granularity: Granularity = Query(Granularity.week, description="Granularity (day, week, month)"),
    days: int = Query(365, ge=0, description="Date window in days (0 for all time)"),
):
    """Return periodic revenue and gross profit series."""
    if is_snapshot_mode():
        g_val = granularity.value if hasattr(granularity, "value") else str(granularity)
        norm_gran = S.normalize_granularity(g_val)
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"trend__granularity-{norm_gran}__days-{norm_days}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.trend(granularity=granularity.value, days=days)


@app.get("/api/top-products")
def top_products(
    days: int = Query(90, ge=0, description="Date window in days (0 for all time)"),
    limit: int = Query(8, ge=1, le=50, description="Max products to return"),
):
    """Return top products sorted by revenue descending."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"top_products__days-{norm_days}.json")
        if data is not None:
            return data[:limit]
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.top_products(days=days, limit=limit)


@app.get("/api/top-customers")
def top_customers(
    days: int = Query(90, ge=0, description="Date window in days (0 for all time)"),
    limit: int = Query(8, ge=1, le=50, description="Max customers to return"),
):
    """Return top customers excluding walk-ins, sorted by revenue descending."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"top_customers__days-{norm_days}.json")
        if data is not None:
            return data[:limit]
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.top_customers(days=days, limit=limit)


@app.get("/api/categories")
def categories(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Return revenue and gross profit by category."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"categories__days-{norm_days}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.categories(days=days)


@app.get("/api/anomalies")
def anomalies(days: int = Query(180, ge=0, description="Date window in days (0 for all time)")):
    """Detect daily revenue anomalies using weekday-normalized rolling z-scores."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"anomalies__days-{norm_days}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.anomalies(days=days)


@app.get("/api/anomalies/explain")
def explain_anomaly(date: str = Query(..., description="Target date in YYYY-MM-DD")):
    """Provide AI 'why' explanation for a revenue spike or drop using top sellers and baseline comparisons."""
    if is_snapshot_mode():
        data = S.get_snapshot(f"explain_anomaly__date-{date}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.explain_anomaly(date)


@app.get("/api/forecast")
def forecast(horizon: int = Query(30, description="Forecast horizon in days (clamped to 7..90)")):
    """Forecast future revenue with confidence bands and backtest metrics."""
    if is_snapshot_mode():
        data = S.get_snapshot("forecast__horizon-30.json") or S.get_snapshot("forecast.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.forecast(horizon=min(max(horizon, 7), 90))


# ---------------------------------------------------------
# Brand Comparison & Inventory Analytics
# ---------------------------------------------------------

@app.get("/api/brands/comparison")
def brands_comparison(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Compare competing brands in product groups that contain 2+ products."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"brands_comparison__days-{norm_days}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.brands_comparison(days=days)


@app.get("/api/inventory/status")
def inventory_status():
    """Return stock status per product and aggregate inventory alert summary."""
    if is_snapshot_mode():
        data = S.get_snapshot("inventory_status.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.inventory_status()


@app.get("/api/reorder/suggestions")
def reorder_suggestions(
    lead_days: int = Query(5, ge=1, le=30, description="Delivery lead time in days"),
    cover_days: int = Query(14, ge=3, le=60, description="Days of stock cover to purchase"),
):
    """Generate purchase recommendations for low stock products."""
    if is_snapshot_mode():
        norm_lead = S.normalize_lead_days(lead_days)
        norm_cover = S.normalize_cover_days(cover_days)
        data = S.get_snapshot(f"reorder_suggestions__lead_days-{norm_lead}__cover_days-{norm_cover}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.reorder_suggestions(lead_days=lead_days, cover_days=cover_days)


@app.get("/api/reorder/export.csv")
def reorder_export_csv(
    lead_days: int = Query(5, ge=1, le=30),
    cover_days: int = Query(14, ge=3, le=60),
):
    """Export purchase recommendations as CSV."""
    if is_snapshot_mode():
        csv_content = S.get_snapshot("reorder_export.csv")
        if csv_content is not None:
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=reorder_suggestions.csv"},
            )
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    data = A.reorder_suggestions(lead_days=lead_days, cover_days=cover_days)
    lines = data["lines"]
    rows = ["manufacturer,product,qty,unit_cost,line_cost"]
    for l in lines:
        mfr = f'"{l["manufacturer"]}"' if "," in l["manufacturer"] else l["manufacturer"]
        prd = f'"{l["product"]}"' if "," in l["product"] else l["product"]
        rows.append(f"{mfr},{prd},{l['suggested_qty']},{l['unit_cost']},{l['line_cost']}")
    csv_content = "\n".join(rows)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reorder_suggestions.csv"},
    )


# ---------------------------------------------------------
# Refill Reminders
# ---------------------------------------------------------

@app.get("/api/refills")
def refills(
    within_days: int = Query(5, ge=1, le=30, description="Window in days to consider refill due soon"),
    include_names: bool = Query(False, description="Whether to include medicine names in responses"),
):
    """Return regular chronic medication refill alerts."""
    if is_snapshot_mode():
        data = S.get_snapshot("refills.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.refills(within_days=within_days, include_names=include_names)


@app.get("/api/refills/message")
def refill_message(
    customer_id: int = Query(..., description="Target customer ID"),
    include_names: bool = Query(False, description="Whether to include medicine names for privacy"),
):
    """Return pre-composed reminder message and WhatsApp click URL."""
    if is_snapshot_mode():
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.refill_message(customer_id=customer_id, include_names=include_names)


# ---------------------------------------------------------
# End-of-Day Summaries
# ---------------------------------------------------------

@app.get("/api/day/summary")
def day_summary(date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (default: last closed date)")):
    """Return comprehensive summary for a closed date."""
    if is_snapshot_mode():
        if date:
            data = S.get_snapshot(f"day_summary__date-{date}.json")
            if data is not None:
                return data
            raise HTTPException(status_code=404, detail=f"Date {date} is not available in the snapshot demo.")
        data = S.get_snapshot("day_summary.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")

    target_date = None
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format, expected YYYY-MM-DD")

    try:
        return A.day_summary(target_date)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/day/summaries")
def day_summaries(limit: int = Query(14, ge=1, le=60, description="Max closed days to return")):
    """Return recent closed days overview."""
    if is_snapshot_mode():
        data = S.get_snapshot("day_summaries__limit-14.json") or S.get_snapshot("day_summaries.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.day_summaries(limit=limit)


# ---------------------------------------------------------
# Profit Leaks & Market Basket Analysis
# ---------------------------------------------------------

@app.get("/api/profit/leaks")
def profit_leaks(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Analyze profit leaks: discount leakage, brand margin gaps, low-margin bestsellers, expiry."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"profit_leaks__days-{norm_days}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.profit_leaks(days=days)


@app.get("/api/basket/pairs")
def basket_pairs(
    days: int = Query(90, ge=0, description="Date window in days"),
    min_count: int = Query(20, ge=1, description="Minimum joint invoice appearances"),
    limit: int = Query(15, ge=1, le=50, description="Max pairs to return"),
):
    """Market-basket analysis returning top product group pairs ranked by lift."""
    if is_snapshot_mode():
        norm_days = S.normalize_days(days)
        data = S.get_snapshot(f"basket_pairs__days-{norm_days}.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.basket_pairs(days=days, min_count=min_count, limit=limit)


@app.get("/api/basket/companions")
def basket_companions(
    product_group: str = Query(..., description="Product group name to find companions for"),
    limit: int = Query(3, ge=1, le=10, description="Max companion items to return"),
):
    """Return top cross-sell companion items for quick addition during billing."""
    if is_snapshot_mode():
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    return A.basket_companions(product_group=product_group, limit=limit)


# ---------------------------------------------------------
# Live Billing & Day Closes
# ---------------------------------------------------------

class LiveBillItem(BaseModel):
    product_id: int
    quantity: int = Field(..., ge=1)


class LiveBillRequest(BaseModel):
    customer_id: int = 1
    items: list[LiveBillItem]
    sale_date: Optional[date] = None


@app.post("/api/sales/live")
def create_live_sale(req: LiveBillRequest, db: Session = Depends(get_db)):
    """
    Record live bill items, decrement inventory FIFO by batch expiry, and store as unclosed sale.
    """
    if is_snapshot_mode():
        raise HTTPException(status_code=403, detail="Write operations are disabled in demo mode.")
    if not req.items:
        raise HTTPException(status_code=422, detail="Items list cannot be empty.")

    tz = ZoneInfo(STORE_TZ)
    now_tz = datetime.now(tz)
    today_tz = now_tz.date()

    bill_date = req.sale_date or today_tz
    if bill_date > today_tz:
        raise HTTPException(status_code=422, detail="Sale date cannot be in the future.")

    # Check if date is already closed
    is_closed = db.query(DayClose).filter(DayClose.date == bill_date).first()
    if is_closed:
        raise HTTPException(status_code=409, detail=f"Date {bill_date.isoformat()} is already closed.")

    # Resolve customer (defaults automatically to Walk-in Customer)
    customer_id = req.customer_id or 1
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        customer = Customer(id=1, name="Walk-in Customer", city="Counter")
        db.add(customer)
        db.commit()
        customer_id = 1

    # Generate live invoice ID: LIVE-YYYYMMDD-XXXX
    date_prefix = f"LIVE-{bill_date.strftime('%Y%m%d')}-"
    last_inv = (
        db.query(Sale.invoice_id)
        .filter(Sale.invoice_id.like(f"{date_prefix}%"))
        .order_by(Sale.id.desc())
        .first()
    )
    if last_inv:
        try:
            seq = int(last_inv[0].split("-")[-1]) + 1
        except Exception:
            seq = 1
    else:
        seq = 1
    invoice_id = f"{date_prefix}{seq:04d}"

    total_amount = 0.0
    inserted_items = []

    for item in req.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=422, detail=f"Product ID {item.product_id} not found.")

        line_total = round(item.quantity * product.unit_price, 2)
        total_amount += line_total

        sale = Sale(
            invoice_id=invoice_id,
            sale_date=bill_date,
            sale_time=now_tz.replace(tzinfo=None),
            customer_id=customer_id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=product.unit_price,
            total_amount=line_total,
            source="live",
        )
        db.add(sale)

        # Decrement inventory batches for this product (FIFO: earliest expiry first)
        batches = (
            db.query(Inventory)
            .filter(Inventory.product_id == item.product_id)
            .order_by(Inventory.expiry_date.asc().nullslast(), Inventory.id.asc())
            .all()
        )
        qty_to_deduct = item.quantity
        for b in batches:
            if b.stock_on_hand > 0:
                deduct = min(b.stock_on_hand, qty_to_deduct)
                b.stock_on_hand -= deduct
                qty_to_deduct -= deduct
                if qty_to_deduct <= 0:
                    break

        inserted_items.append({
            "product_id": item.product_id,
            "product": product.name,
            "quantity": item.quantity,
            "unit_price": product.unit_price,
            "line_total": line_total,
        })

    db.commit()
    A.clear_cache()

    return {
        "invoice_id": invoice_id,
        "sale_date": bill_date.isoformat(),
        "customer_id": req.customer_id,
        "items": inserted_items,
        "total_amount": round(total_amount, 2),
    }


@app.get("/api/day/status")
def day_status(db: Session = Depends(get_db)):
    """Return day closing status: last closed date, open days with invoice/line counts (no revenue)."""
    if is_snapshot_mode():
        data = S.get_snapshot("day_status.json")
        if data is not None:
            return data
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")

    tz = ZoneInfo(STORE_TZ)
    today_tz = datetime.now(tz).date()

    last_closed = db.execute(text("SELECT MAX(date) FROM day_closes")).scalar()

    # Query distinct open sale dates
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

    p1 = db.query(Product).filter(Product.id == 1).first()
    is_mock = bool(p1 and p1.name and "Metformin" in p1.name)

    return {
        "last_closed_date": last_closed.isoformat() if hasattr(last_closed, "isoformat") else str(last_closed) if last_closed else None,
        "open_days": open_days,
        "today": today_tz.isoformat(),
        "is_mock_data": is_mock,
    }


class DayCloseRequest(BaseModel):
    date: date


@app.post("/api/day/close")
def close_day(req: DayCloseRequest, db: Session = Depends(get_db)):
    """
    Close a business day in sequential order. Computes invoices and revenue,
    updates day_closes, clears analytics cache, and returns closed day summary.
    """
    if is_snapshot_mode():
        raise HTTPException(status_code=403, detail="Write operations are disabled in demo mode.")
    target_date = req.date
    tz = ZoneInfo(STORE_TZ)
    today_tz = datetime.now(tz).date()

    if target_date > today_tz:
        raise HTTPException(status_code=422, detail="Cannot close a future date.")

    # Check if already closed
    existing = db.query(DayClose).filter(DayClose.date == target_date).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Date {target_date.isoformat()} is already closed.")

    # Verify no earlier sale date is left open (days must be closed in chronological order)
    earlier_open = db.execute(text("""
        SELECT MIN(sale_date) FROM sales
        WHERE sale_date < :target_date AND sale_date NOT IN (SELECT date FROM day_closes)
    """), {"target_date": str(target_date)}).scalar()

    if earlier_open:
        e_str = earlier_open.isoformat() if hasattr(earlier_open, "isoformat") else str(earlier_open)
        raise HTTPException(
            status_code=409,
            detail=f"Earlier date {e_str} is still open. Days must be closed in sequential order."
        )

    # Compute invoices and revenue from sales
    sales_agg = db.execute(text("""
        SELECT COUNT(DISTINCT invoice_id) AS inv_count, COALESCE(SUM(total_amount), 0.0) AS rev
        FROM sales
        WHERE sale_date = :target_date
    """), {"target_date": str(target_date)}).fetchone()

    invoices = int(sales_agg.inv_count or 0)
    revenue = float(round(sales_agg.rev or 0.0, 2))

    day_close = DayClose(
        date=target_date,
        closed_at=datetime.utcnow(),
        invoices=invoices,
        revenue=revenue,
    )
    db.add(day_close)
    db.commit()

    A.clear_cache()

    summary = A.day_summary(target_date)
    email_digest = ED.send_daily_digest(target_date)

    return {
        "status": "ok",
        "date": target_date.isoformat(),
        "invoices": invoices,
        "revenue": revenue,
        "summary": summary,
        "email_digest": email_digest,
    }


@app.post("/api/day/close-due")
def close_due_days(
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
    db: Session = Depends(get_db)
):
    """
    Automated cron endpoint to close all unclosed days strictly before today in order.
    Requires valid X-Cron-Secret header.
    """
    if is_snapshot_mode():
        raise HTTPException(status_code=403, detail="Write operations are disabled in demo mode.")
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid cron secret.")

    tz = ZoneInfo(STORE_TZ)
    today_tz = datetime.now(tz).date()

    open_dates = db.execute(text("""
        SELECT DISTINCT sale_date FROM sales
        WHERE sale_date < :today AND sale_date NOT IN (SELECT date FROM day_closes)
        ORDER BY sale_date ASC
    """), {"today": str(today_tz)}).fetchall()

    closed_results = []
    for row in open_dates:
        d = row.sale_date
        if isinstance(d, str):
            d = datetime.strptime(d, "%Y-%m-%d").date()

        agg = db.execute(text("""
            SELECT COUNT(DISTINCT invoice_id) AS inv_count, COALESCE(SUM(total_amount), 0.0) AS rev
            FROM sales WHERE sale_date = :d
        """), {"d": str(d)}).fetchone()

        inv = int(agg.inv_count or 0)
        rev = float(round(agg.rev or 0.0, 2))

        dc = DayClose(date=d, closed_at=datetime.utcnow(), invoices=inv, revenue=rev)
        db.add(dc)
        db.commit()

        closed_results.append({
            "date": d.isoformat(),
            "invoices": inv,
            "revenue": rev,
        })

    A.clear_cache()
    return {"closed": closed_results}


# ---------------------------------------------------------
# Chat Assistant
# ---------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
def chat(req: ChatRequest):
    """AI BI Assistant chat endpoint."""
    return C.handle_chat_message(req.message)


# ---------------------------------------------------------
# Reports & Accountant Export (Excel & PDF)
# ---------------------------------------------------------

@app.get("/api/reports/export/excel")
def export_accountant_excel(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Generate and download multi-sheet Excel financial report for accountant."""
    if is_snapshot_mode():
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    excel_bytes = R.generate_accountant_excel(days=days)
    filename = f"company_brain_accountant_report_{days}days.xlsx" if days > 0 else "company_brain_accountant_report_all_time.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/reports/export/pdf")
def export_accountant_pdf(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Generate and download official PDF audit & financial statement for accountant."""
    if is_snapshot_mode():
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    pdf_bytes = R.generate_accountant_pdf(days=days)
    filename = f"company_brain_financial_statement_{days}days.pdf" if days > 0 else "company_brain_financial_statement_all_time.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ---------------------------------------------------------
# Daily Email Digest
# ---------------------------------------------------------

class EmailDigestRequest(BaseModel):
    date: date
    recipient: Optional[str] = None


@app.post("/api/day/email-digest")
def trigger_email_digest(req: EmailDigestRequest):
    """Manually dispatch daily email digest for a specific closed date."""
    if is_snapshot_mode():
        raise HTTPException(status_code=403, detail="Write operations are disabled in demo mode.")
    return ED.send_daily_digest(req.date, req.recipient)


@app.get("/api/day/email-preview")
def preview_email_digest(date: date = Query(..., description="Target closed business date")):
    """Preview the exact HTML email digest for a closed date directly in the browser."""
    if is_snapshot_mode():
        raise HTTPException(status_code=404, detail="Not available in the snapshot demo.")
    _, _, html_content = ED.generate_email_content(date)
    return Response(content=html_content, media_type="text/html")
