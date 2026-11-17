from datetime import date, datetime, timedelta
from enum import Enum
import json
import math
import os
import time
from typing import Any, Optional
from urllib.parse import quote
import numpy as np
import pandas as pd
from sqlalchemy import text
from .db import DayClose, Customer, Product, engine, SessionLocal


class Granularity(str, Enum):
    day = "day"
    week = "week"
    month = "month"


# In-memory DataFrame cache with TTL
_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str, loader_fn, ttl: float = 120.0) -> Any:
    now = time.time()
    if key in _cache:
        cached_time, cached_val = _cache[key]
        if now - cached_time < ttl:
            if isinstance(cached_val, pd.DataFrame):
                return cached_val.copy()
            return cached_val
    val = loader_fn()
    _cache[key] = (now, val)
    if isinstance(val, pd.DataFrame):
        return val.copy()
    return val


def clear_cache() -> None:
    """Clear in-memory cache when sales or day closes change."""
    _cache.clear()


def get_last_closed_date() -> Optional[date]:
    """Return max closed date from day_closes, or None if no days closed."""
    with engine.connect() as conn:
        res = conn.execute(text("SELECT MAX(date) FROM day_closes")).scalar()
        if res is not None:
            if isinstance(res, str):
                return datetime.strptime(res, "%Y-%m-%d").date()
            if isinstance(res, datetime):
                return res.date()
            return res
    return None


def sales_df() -> pd.DataFrame:
    """
    Return closed sales joined with products and customers, with cogs computed.
    Analytics strictly end on or before the last closed date. Cached for 120s.
    """
    def _load():
        last_closed = get_last_closed_date()
        if last_closed is None:
            # No closed days yet: return empty dataframe with expected schema
            return pd.DataFrame(columns=[
                "id", "invoice_id", "sale_date", "sale_time", "customer_id", "product_id",
                "quantity", "unit_price", "total_amount", "source", "product", "category",
                "unit_cost", "product_unit_price", "product_group", "manufacturer",
                "customer", "cogs"
            ])

        sql = """
        SELECT s.id, s.invoice_id, s.sale_date, s.sale_time, s.customer_id, s.product_id,
               s.quantity, s.unit_price, s.total_amount, s.source,
               p.name AS product, p.category, p.unit_cost, p.unit_price AS product_unit_price,
               COALESCE(NULLIF(p.product_group, ''), p.name) AS product_group,
               COALESCE(NULLIF(p.manufacturer, ''), 'Unknown') AS manufacturer,
               COALESCE(c.name, 'Walk-in Customer') AS customer
        FROM sales s
        JOIN products p ON s.product_id = p.id
        LEFT JOIN customers c ON s.customer_id = c.id
        WHERE s.sale_date <= :last_closed
        """
        with engine.connect() as conn:
            df = pd.read_sql(
                text(sql),
                conn,
                params={"last_closed": str(last_closed)},
                parse_dates=["sale_date"]
            )
        if df.empty:
            df["cogs"] = pd.Series(dtype=float)
            return df
        df["cogs"] = df["quantity"] * df["unit_cost"]
        return df

    return _get_cached("sales", _load, ttl=120.0)


def expenses_df() -> pd.DataFrame:
    """Return expenses table. Cached for 120s."""
    def _load():
        sql = "SELECT id, expense_date, category, amount FROM expenses"
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, parse_dates=["expense_date"])

    return _get_cached("expenses", _load, ttl=120.0)


def _prorated_expenses(e: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Each expense covers its calendar month; prorate by days falling in [start, end]."""
    if e.empty:
        return 0.0

    period = e["expense_date"].dt.to_period("M")
    month_start = period.dt.start_time
    month_end = period.dt.end_time.dt.normalize()
    days_in_month = e["expense_date"].dt.days_in_month

    overlap_start = month_start.clip(lower=start)
    overlap_end = month_end.clip(upper=end)
    overlap_days = (overlap_end - overlap_start).dt.days + 1
    overlap_days = overlap_days.clip(lower=0)

    prorated = e["amount"] * (overlap_days / days_in_month)
    return float(round(prorated.sum(), 2))


def _filter_window(s: pd.DataFrame, days: int) -> pd.DataFrame:
    """Filter sales DataFrame for window ending on latest sale_date. days=0 means all time."""
    if s.empty or days <= 0:
        return s
    latest_date = s["sale_date"].max()
    start_date = latest_date - pd.Timedelta(days=days - 1)
    return s[(s["sale_date"] >= start_date) & (s["sale_date"] <= latest_date)]


def kpis(days: int = 90) -> dict[str, Any]:
    """Calculate KPI metrics for the given window of days."""
    s = sales_df()
    e = expenses_df()

    if s.empty:
        empty_res = {
            "revenue": 0.0,
            "cogs": 0.0,
            "gross_profit": 0.0,
            "expenses": 0.0,
            "net_profit": 0.0,
            "margin": 0.0,
            "orders": 0,
            "customers": 0,
            "aov": 0.0,
            "days": days,
        }
        if days > 0:
            empty_res["revenue_growth"] = None
            empty_res["profit_growth"] = None
        return empty_res

    latest = s["sale_date"].max()
    earliest = s["sale_date"].min()

    def calc_window(start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
        sw = s[(s["sale_date"] >= start) & (s["sale_date"] <= end)]
        rev = float(round(sw["total_amount"].sum(), 2))
        cogs = float(round(sw["cogs"].sum(), 2))
        gross_profit = float(round(rev - cogs, 2))
        exp = _prorated_expenses(e, start, end)
        net_profit = float(round(gross_profit - exp, 2))
        orders = int(sw["invoice_id"].nunique())
        customers = int(sw["customer_id"].nunique())
        margin = float(round((net_profit / rev * 100), 2)) if rev > 0 else 0.0
        aov = float(round(rev / orders, 2)) if orders > 0 else 0.0
        return {
            "revenue": rev,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "expenses": exp,
            "net_profit": net_profit,
            "margin": margin,
            "orders": orders,
            "customers": customers,
            "aov": aov,
        }

    if days > 0:
        step = pd.Timedelta(days=days)
        start = latest - step + pd.Timedelta(days=1)
        cur = calc_window(start, latest)

        prev_end = latest - step
        prev_start = prev_end - step + pd.Timedelta(days=1)
        prev = calc_window(prev_start, prev_end)

        cur["revenue_growth"] = (
            float(round((cur["revenue"] - prev["revenue"]) / prev["revenue"] * 100, 2))
            if prev["revenue"]
            else None
        )
        cur["profit_growth"] = (
            float(round((cur["net_profit"] - prev["net_profit"]) / abs(prev["net_profit"]) * 100, 2))
            if prev["net_profit"]
            else None
        )
        cur["days"] = days
        return cur
    else:
        cur = calc_window(earliest, latest)
        cur["days"] = 0
        return cur


def trend(granularity: str = "week", days: int = 365) -> list[dict[str, Any]]:
    """Return periodic revenue and gross profit series."""
    s = sales_df()
    if s.empty:
        return []

    sw = _filter_window(s, days)
    if sw.empty:
        return []

    rule_map = {
        "day": "D",
        "week": "W-SUN",
        "month": "MS",
    }
    rule = rule_map.get(granularity, "W-SUN")

    g = (
        sw.set_index("sale_date")
        .resample(rule)
        .agg(
            revenue=("total_amount", "sum"),
            cogs=("cogs", "sum"),
        )
        .reset_index()
    )
    g["profit"] = (g["revenue"] - g["cogs"]).round(2)
    g["revenue"] = g["revenue"].round(2)
    g["period"] = g["sale_date"].dt.strftime("%Y-%m-%d")
    return json.loads(g[["period", "revenue", "profit"]].to_json(orient="records"))


def top_products(days: int = 90, limit: int = 8) -> list[dict[str, Any]]:
    """Return top products sorted by revenue descending."""
    s = sales_df()
    if s.empty:
        return []

    sw = _filter_window(s, days)
    if sw.empty:
        return []

    g = (
        sw.groupby(["product", "category"])
        .agg(
            revenue=("total_amount", "sum"),
            units=("quantity", "sum"),
            cogs=("cogs", "sum"),
        )
        .reset_index()
    )
    g["profit"] = (g["revenue"] - g["cogs"]).round(2)
    g["margin_pct"] = (g["profit"] / g["revenue"] * 100).round(2).fillna(0.0)
    g["revenue"] = g["revenue"].round(2)
    g["units"] = g["units"].astype(int)

    ranked = g.sort_values("revenue", ascending=False).head(limit).drop(columns=["cogs"])
    return json.loads(ranked.to_json(orient="records"))


def top_customers(days: int = 90, limit: int = 8) -> list[dict[str, Any]]:
    """Return top customers excluding walk-ins, sorted by revenue descending."""
    s = sales_df()
    if s.empty:
        return []

    sw = _filter_window(s, days)
    sw = sw[~sw["customer"].str.startswith("Walk-in")]
    if sw.empty:
        return []

    g = (
        sw.groupby("customer")
        .agg(
            revenue=("total_amount", "sum"),
            orders=("invoice_id", "nunique"),
        )
        .reset_index()
    )
    g["revenue"] = g["revenue"].round(2)
    g["orders"] = g["orders"].astype(int)

    ranked = g.sort_values("revenue", ascending=False).head(limit)
    return json.loads(ranked.to_json(orient="records"))


def categories(days: int = 90) -> list[dict[str, Any]]:
    """Return revenue and gross profit grouped by product category."""
    s = sales_df()
    if s.empty:
        return []

    sw = _filter_window(s, days)
    if sw.empty:
        return []

    g = (
        sw.groupby("category")
        .agg(
            revenue=("total_amount", "sum"),
            cogs=("cogs", "sum"),
        )
        .reset_index()
    )
    g["profit"] = (g["revenue"] - g["cogs"]).round(2)
    g["revenue"] = g["revenue"].round(2)

    ranked = g.drop(columns=["cogs"]).sort_values("revenue", ascending=False)
    return json.loads(ranked.to_json(orient="records"))


def daily() -> pd.Series:
    """Return total revenue per calendar day from sales_df(), reindexed with 0 for missing days."""
    s = sales_df()
    if s.empty:
        return pd.Series(dtype=float)
    d = s.groupby("sale_date")["total_amount"].sum()
    full_index = pd.date_range(d.index.min(), d.index.max(), freq="D")
    return d.reindex(full_index, fill_value=0.0)


def anomalies(days: int = 180) -> dict[str, Any]:
    """Detect daily revenue anomalies using weekday-normalized rolling z-scores."""
    d = daily()
    if d.empty or len(d) < 15:
        return {"series": [], "flagged": []}

    overall_mean = d.mean() or 1.0
    factor = d.groupby(d.index.dayofweek).mean() / overall_mean
    adj = d / d.index.dayofweek.map(factor).values

    base = adj.shift(1).rolling(28, min_periods=14)
    base_mean = base.mean()
    base_std = base.std().replace(0, np.nan)
    z = (adj - base_mean) / base_std

    df = pd.DataFrame({
        "date": d.index.strftime("%Y-%m-%d"),
        "revenue": d.values.round(2),
        "z": z.values.round(2),
    }).dropna()

    df["is_anomaly"] = (df["z"].abs() > 3).astype(bool)
    df["type"] = np.where(df["z"] > 0, "spike", "drop")

    if days > 0:
        df = df.tail(days)

    flagged = df[df["is_anomaly"]]
    flagged_records = json.loads(flagged.to_json(orient="records"))

    # Enrich each flagged anomaly with top-sellers and plain-English AI "why" explanation
    for item in flagged_records:
        exp = explain_anomaly(item["date"])
        item["explanation"] = exp["explanation"]
        item["top_products"] = exp["top_products"]
        item["baseline_revenue"] = exp["baseline_revenue"]
        item["diff_pct"] = exp["diff_pct"]

    return {
        "series": json.loads(df.to_json(orient="records")),
        "flagged": flagged_records,
    }


def explain_anomaly(target_date: Any) -> dict[str, Any]:
    """
    Explain why a specific date was a revenue spike or drop using that day's top sellers,
    order counts, and comparison against baseline weekday averages.
    """
    if isinstance(target_date, str):
        target_str = target_date
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        except Exception:
            dt = None
    elif isinstance(target_date, (datetime, date)):
        dt = target_date.date() if isinstance(target_date, datetime) else target_date
        target_str = dt.strftime("%Y-%m-%d")
    else:
        dt = None
        target_str = str(target_date)

    s = sales_df()
    if s.empty:
        return {
            "date": target_str,
            "type": "normal",
            "revenue": 0.0,
            "baseline_revenue": 0.0,
            "diff_pct": 0.0,
            "invoices": 0,
            "top_products": [],
            "explanation": f"No sales data recorded for {target_str}.",
        }

    day_sales = s[s["sale_date"].dt.strftime("%Y-%m-%d") == target_str]
    d = daily()

    weekday = dt.weekday() if dt else 0
    weekday_name = dt.strftime("%A") if dt else "day"

    # Find rolling 4-week average for same weekday prior to target date
    prior_d = d[d.index.date < dt] if (dt and not d.empty) else d
    same_weekday_prior = prior_d[prior_d.index.dayofweek == weekday] if not prior_d.empty else pd.Series(dtype=float)
    if len(same_weekday_prior) >= 2:
        baseline_rev = float(same_weekday_prior.tail(4).mean())
    elif not d.empty:
        baseline_rev = float(d.mean())
    else:
        baseline_rev = 1.0

    baseline_rev = round(baseline_rev, 2)
    actual_rev = float(day_sales["total_amount"].sum()) if not day_sales.empty else 0.0
    actual_rev = round(actual_rev, 2)
    invoices = int(day_sales["invoice_id"].nunique()) if not day_sales.empty else 0

    diff_pct = round(((actual_rev - baseline_rev) / baseline_rev * 100), 1) if baseline_rev > 0 else 0.0
    anom_type = "spike" if actual_rev >= baseline_rev else "drop"

    top_products = []
    if not day_sales.empty:
        agg = day_sales.groupby("product").agg(
            units=("quantity", "sum"),
            revenue=("total_amount", "sum")
        ).reset_index().sort_values("revenue", ascending=False)

        for _, r in agg.head(3).iterrows():
            rev = float(r["revenue"])
            share = round((rev / actual_rev * 100), 1) if actual_rev > 0 else 0.0
            top_products.append({
                "product": r["product"],
                "units": int(r["units"]),
                "revenue": round(rev, 2),
                "share_pct": share,
            })

    formatted_date = dt.strftime("%-d %b %Y") if dt else target_str
    if anom_type == "spike":
        if top_products:
            prod_highlights = ", ".join(
                f"{p['product']} ({p['units']} units, ₹{int(round(p['revenue'])):,})" for p in top_products
            )
            explanation = (
                f"On {formatted_date}, revenue spiked to ₹{int(round(actual_rev)):,} (+{diff_pct}% above the usual {weekday_name} average of ₹{int(round(baseline_rev)):,}). "
                f"The spike was driven by strong sales in: {prod_highlights} across {invoices} orders."
            )
        else:
            explanation = (
                f"On {formatted_date}, revenue spiked to ₹{int(round(actual_rev)):,} (+{diff_pct}% above usual {weekday_name} average) across {invoices} orders."
            )
    else:
        if top_products:
            prod_highlights = ", ".join(
                f"{p['product']} ({p['units']} units, ₹{int(round(p['revenue'])):,})" for p in top_products
            )
            explanation = (
                f"On {formatted_date}, revenue dropped to ₹{int(round(actual_rev)):,} ({diff_pct}% below the usual {weekday_name} average of ₹{int(round(baseline_rev)):,}). "
                f"Only {invoices} orders were billed, with top sales from {prod_highlights}."
            )
        else:
            explanation = (
                f"On {formatted_date}, revenue dropped to ₹{int(round(actual_rev)):,} ({diff_pct}% below usual {weekday_name} average) with only {invoices} orders."
            )

    return {
        "date": target_str,
        "type": anom_type,
        "revenue": actual_rev,
        "baseline_revenue": baseline_rev,
        "diff_pct": diff_pct,
        "invoices": invoices,
        "top_products": top_products,
        "explanation": explanation,
    }


def _fit_predict(train: pd.Series, dates: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Fit robust trend with weekday seasonality and predict future dates with confidence bands."""
    weekday_median = train.groupby(train.index.dayofweek).median()
    overall_median = train.median() or 1.0
    factor = weekday_median / overall_median

    adj = train / train.index.dayofweek.map(factor).values
    adj_84 = adj.tail(84)
    med = adj_84.median()
    mad = float((adj_84 - med).abs().median()) or 1.0
    adj_clipped = adj_84.clip(med - 3 * 1.4826 * mad, med + 3 * 1.4826 * mad)

    x = np.arange(len(adj_clipped))
    slope, icpt = np.polyfit(x, adj_clipped.values, 1)
    resid = float(np.std(adj_clipped.values - (slope * x + icpt)))

    xf = len(adj_clipped) + np.arange(len(dates))
    f = dates.dayofweek.map(factor).values
    mid = (slope * xf + icpt) * f
    band = 1.96 * resid * f
    return mid, band


def forecast(horizon: int = 30) -> dict[str, Any]:
    """Forecast future revenue using robust seasonal linear trend and backtest performance."""
    d = daily()
    if d.empty or len(d) < 35:
        return {
            "history": [],
            "forecast": [],
            "total_forecast": 0.0,
            "backtest": {"model_mae": 0.0, "naive_mae": 0.0, "improvement_pct": None},
        }

    clamped_horizon = min(max(horizon, 7), 90)
    hold = 28
    train, test = d.iloc[:-hold], d.iloc[-hold:]
    pred_mid, _ = _fit_predict(train, test.index)
    pred = np.clip(pred_mid, 0, None)

    naive = np.array([train[train.index.dayofweek == dw].tail(4).mean() for dw in test.index.dayofweek])
    mae_model = float(np.mean(np.abs(test.values - pred)))
    mae_naive = float(np.mean(np.abs(test.values - naive)))
    improvement_pct = round((1 - mae_model / mae_naive) * 100, 1) if mae_naive else None

    future = pd.date_range(d.index.max() + pd.Timedelta(days=1), periods=clamped_horizon, freq="D")
    mid, band = _fit_predict(d, future)

    forecast_vals = np.clip(mid, 0, None).round(2)
    lower_vals = np.clip(mid - band, 0, None).round(2)
    upper_vals = (mid + band).round(2)

    f_df = pd.DataFrame({
        "date": future.strftime("%Y-%m-%d"),
        "forecast": forecast_vals,
        "lower": lower_vals,
        "upper": upper_vals,
    })

    h = d.tail(60)
    hist_df = pd.DataFrame({
        "date": h.index.strftime("%Y-%m-%d"),
        "actual": h.values.round(2),
    })

    return {
        "history": json.loads(hist_df.to_json(orient="records")),
        "forecast": json.loads(f_df.to_json(orient="records")),
        "total_forecast": round(float(f_df["forecast"].sum()), 2),
        "backtest": {
            "model_mae": round(mae_model, 2),
            "naive_mae": round(mae_naive, 2),
            "improvement_pct": improvement_pct,
        },
    }


def brands_comparison(days: int = 90) -> list[dict[str, Any]]:
    """
    Compare competing brands in product groups that contain 2+ products.
    Calculations use closed days ending at the last closed date.
    """
    with engine.connect() as conn:
        prod_rows = conn.execute(text("""
            SELECT id, name, category, unit_cost, unit_price,
                   COALESCE(NULLIF(product_group, ''), name) AS p_group,
                   COALESCE(NULLIF(manufacturer, ''), 'Unknown') AS mfr
            FROM products
        """)).fetchall()

        # Query total stock_on_hand per product
        inv_rows = conn.execute(text("""
            SELECT product_id, SUM(stock_on_hand) AS total_stock
            FROM inventory
            GROUP BY product_id
        """)).fetchall()

    if not prod_rows:
        return []

    stock_map = {row.product_id: int(row.total_stock or 0) for row in inv_rows}

    # Group products by group
    groups_dict: dict[str, list[Any]] = {}
    for p in prod_rows:
        groups_dict.setdefault(p.p_group, []).append(p)

    # Filter to groups with 2+ products
    competing_groups = {g: prods for g, prods in groups_dict.items() if len(prods) >= 2}
    if not competing_groups:
        return []

    s = sales_df()
    sw = _filter_window(s, days)

    result = []
    effective_days = days if days > 0 else (
        (s["sale_date"].max() - s["sale_date"].min()).days + 1 if not s.empty else 90
    )
    if effective_days <= 0:
        effective_days = 90

    for g_name, prods in competing_groups.items():
        prod_ids = [p.id for p in prods]
        g_sales = sw[sw["product_id"].isin(prod_ids)] if not sw.empty else pd.DataFrame()

        # Calculate sales metrics per product in window
        sales_summary = {}
        if not g_sales.empty:
            agg = g_sales.groupby("product_id").agg(
                units=("quantity", "sum"),
                revenue=("total_amount", "sum"),
                cogs=("cogs", "sum")
            ).reset_index()
            for _, r in agg.iterrows():
                sales_summary[int(r["product_id"])] = {
                    "units": int(r["units"]),
                    "revenue": float(round(r["revenue"], 2)),
                    "cogs": float(round(r["cogs"], 2)),
                }

        brand_items = []
        total_units = 0
        total_rev = 0.0

        for p in prods:
            s_data = sales_summary.get(p.id, {"units": 0, "revenue": 0.0, "cogs": 0.0})
            u = s_data["units"]
            r = s_data["revenue"]
            profit = round(r - s_data["cogs"], 2)
            margin_pct = round(profit / r * 100, 2) if r > 0 else 0.0
            stock = stock_map.get(p.id, 0)
            avg_daily = u / float(effective_days)
            doc = round(stock / avg_daily, 1) if avg_daily > 0 else None

            total_units += u
            total_rev += r

            brand_items.append({
                "product_id": p.id,
                "product": p.name,
                "manufacturer": p.mfr,
                "units": u,
                "revenue": r,
                "profit": profit,
                "margin_pct": margin_pct,
                "stock_on_hand": stock,
                "days_of_cover": doc,
            })

        # Determine leader (max units, then max revenue)
        brand_items.sort(key=lambda b: (b["units"], b["revenue"]), reverse=True)
        leader_brand = brand_items[0]
        leader_units = leader_brand["units"]

        min_share = 100.0
        for b in brand_items:
            share = round(b["units"] / total_units * 100, 1) if total_units > 0 else 0.0
            b["share_pct"] = share
            if share < min_share:
                min_share = share

            if b["product"] == leader_brand["product"]:
                b["vs_leader"] = None
                b["flag"] = "leader"
            else:
                b["vs_leader"] = round(leader_units / b["units"], 1) if b["units"] > 0 else None
                b["flag"] = "underperforming" if share < 10.0 else None

        # Build plain-English insight
        underperforming = [b for b in brand_items if b["flag"] == "underperforming"]
        insight = ""
        if underperforming and leader_units > 0:
            target = underperforming[0]
            mfr_lead = leader_brand["manufacturer"] if leader_brand["manufacturer"] != "Unknown" else leader_brand["product"]
            mfr_target = target["manufacturer"] if target["manufacturer"] != "Unknown" else target["product"]
            if target["units"] > 0 and target["vs_leader"] is not None:
                ratio = int(round(target["vs_leader"])) if target["vs_leader"] >= 5 else target["vs_leader"]
                doc_str = f", about {int(round(target['days_of_cover']))} days of supply" if target["days_of_cover"] else ""
                insight = (
                    f"{mfr_lead} sells {ratio}x more than {mfr_target} in {g_name}. "
                    f"{mfr_target} has {target['stock_on_hand']} units in stock{doc_str}."
                )
            else:
                insight = (
                    f"{mfr_lead} dominates {g_name} with {leader_units} units sold while {mfr_target} had zero sales. "
                    f"{mfr_target} has {target['stock_on_hand']} units in stock."
                )
        elif total_units > 0:
            mfr_lead = leader_brand["manufacturer"] if leader_brand["manufacturer"] != "Unknown" else leader_brand["product"]
            insight = f"{mfr_lead} leads {g_name} with {leader_brand['share_pct']}% share across {len(brand_items)} brands."
        else:
            insight = f"{len(brand_items)} brands available in {g_name} with no sales recorded in this period."

        result.append({
            "product_group": g_name,
            "total_units": total_units,
            "total_revenue": round(total_rev, 2),
            "leader": leader_brand["product"],
            "brands": brand_items,
            "insight": insight,
            "_min_share": min_share,
        })

    # Sort groups by how imbalanced they are (smallest brand share first)
    result.sort(key=lambda g: g["_min_share"])
    for g in result:
        del g["_min_share"]

    return result


def inventory_status() -> dict[str, Any]:
    """
    Return stock status per product and aggregate inventory summary.
    Reference date for expiry calculation is the last closed date (or today).
    """
    last_closed = get_last_closed_date()
    today_dt = date.today()
    ref_date = last_closed or today_dt

    with engine.connect() as conn:
        prod_rows = conn.execute(text("""
            SELECT id, name, category, unit_cost, unit_price,
                   COALESCE(NULLIF(manufacturer, ''), 'Unknown') AS manufacturer
            FROM products
        """)).fetchall()

        inv_rows = conn.execute(text("""
            SELECT product_id, stock_on_hand, reorder_level, expiry_date
            FROM inventory
        """)).fetchall()

    if not prod_rows:
        return {
            "summary": {
                "capital_tied_up_overstock": 0.0,
                "value_expiring_soon": 0.0,
                "items_to_reorder": 0,
            },
            "products": [],
        }

    # Aggregate inventory by product
    inv_by_prod: dict[int, dict[str, Any]] = {}
    for r in inv_rows:
        pid = r.product_id
        if pid not in inv_by_prod:
            inv_by_prod[pid] = {
                "stock": 0,
                "reorder_level": r.reorder_level or 0,
                "expiries": []
            }
        inv_by_prod[pid]["stock"] += (r.stock_on_hand or 0)
        if r.reorder_level:
            inv_by_prod[pid]["reorder_level"] = max(inv_by_prod[pid]["reorder_level"], r.reorder_level)
        if r.expiry_date:
            exp = r.expiry_date
            if isinstance(exp, str):
                exp = datetime.strptime(exp, "%Y-%m-%d").date()
            elif isinstance(exp, datetime):
                exp = exp.date()
            inv_by_prod[pid]["expiries"].append(exp)

    # 90-day sales for avg_daily_units and 60-day sales for dead stock check
    s = sales_df()
    units_90: dict[int, int] = {}
    units_60: dict[int, int] = {}

    if not s.empty:
        max_date = s["sale_date"].max()
        start_90 = max_date - pd.Timedelta(days=89)
        start_60 = max_date - pd.Timedelta(days=59)

        s90 = s[s["sale_date"] >= start_90]
        s60 = s[s["sale_date"] >= start_60]

        if not s90.empty:
            units_90 = s90.groupby("product_id")["quantity"].sum().to_dict()
        if not s60.empty:
            units_60 = s60.groupby("product_id")["quantity"].sum().to_dict()

    items = []
    capital_overstock = 0.0
    value_expiring = 0.0
    items_reorder = 0

    for p in prod_rows:
        inv = inv_by_prod.get(p.id, {"stock": 0, "reorder_level": 0, "expiries": []})
        stock = inv["stock"]
        reorder_lvl = inv["reorder_level"]
        expiries = inv["expiries"]
        nearest_exp = min(expiries) if expiries else None
        days_to_exp = (nearest_exp - ref_date).days if nearest_exp else None

        u90 = units_90.get(p.id, 0)
        avg_daily = round(u90 / 90.0, 2)
        doc = round(stock / avg_daily, 1) if avg_daily > 0 else None
        stock_val = round(stock * p.unit_cost, 2)

        u60 = units_60.get(p.id, 0)

        # Status rules in order:
        # 1. expiring_soon: expiry within 60 days of latest sale date and stock > 0
        # 2. reorder: days_of_cover < 7 or stock <= reorder_level
        # 3. overstocked: days_of_cover > 90
        # 4. dead_stock: stock > 0 and no sales in 60 days
        # 5. ok
        if nearest_exp and days_to_exp is not None and days_to_exp <= 60 and stock > 0:
            status = "expiring_soon"
        elif (doc is not None and doc < 7) or (stock <= reorder_lvl and reorder_lvl > 0):
            status = "reorder"
        elif doc is not None and doc > 90:
            status = "overstocked"
        elif stock > 0 and u60 == 0:
            status = "dead_stock"
        else:
            status = "ok"

        if status == "expiring_soon":
            value_expiring += stock_val
        elif status == "overstocked" and doc is not None:
            excess_units = max(0, stock - 90 * avg_daily)
            capital_overstock += excess_units * p.unit_cost
        elif status == "reorder":
            items_reorder += 1

        items.append({
            "product_id": p.id,
            "product": p.name,
            "manufacturer": p.manufacturer,
            "stock_on_hand": stock,
            "avg_daily_units": avg_daily,
            "days_of_cover": doc,
            "stock_value": stock_val,
            "nearest_expiry": nearest_exp.isoformat() if nearest_exp else None,
            "days_to_expiry": days_to_exp,
            "status": status,
        })

    return {
        "summary": {
            "capital_tied_up_overstock": round(capital_overstock, 2),
            "value_expiring_soon": round(value_expiring, 2),
            "items_to_reorder": items_reorder,
        },
        "products": items,
    }


def reorder_suggestions(lead_days: int = 5, cover_days: int = 14) -> dict[str, Any]:
    """
    Generate purchase recommendations for products needing restock based on 60-day demand.
    Excludes overstocked, expiring, and zero-sales items.
    """
    lead_days = min(max(lead_days, 1), 30)
    cover_days = min(max(cover_days, 3), 60)

    last_closed = get_last_closed_date()
    ref_date = last_closed or date.today()

    with engine.connect() as conn:
        prod_rows = conn.execute(text("""
            SELECT id, name, category, unit_cost, unit_price,
                   COALESCE(NULLIF(manufacturer, ''), 'Unknown') AS manufacturer
            FROM products
        """)).fetchall()

        inv_rows = conn.execute(text("""
            SELECT product_id, stock_on_hand, expiry_date
            FROM inventory
        """)).fetchall()

    if not prod_rows:
        return {
            "lines": [],
            "by_manufacturer": [],
            "total_cost": 0.0,
            "do_not_reorder": [],
        }

    # Aggregate inventory
    stock_by_prod: dict[int, int] = {}
    exp_by_prod: dict[int, list[date]] = {}
    for r in inv_rows:
        pid = r.product_id
        stock_by_prod[pid] = stock_by_prod.get(pid, 0) + (r.stock_on_hand or 0)
        if r.expiry_date:
            exp = r.expiry_date
            if isinstance(exp, str):
                exp = datetime.strptime(exp, "%Y-%m-%d").date()
            elif isinstance(exp, datetime):
                exp = exp.date()
            exp_by_prod.setdefault(pid, []).append(exp)

    # 60-day daily sales per product
    s = sales_df()
    daily_sales_by_prod: dict[int, pd.Series] = {}
    if not s.empty:
        max_date = s["sale_date"].max()
        start_60 = max_date - pd.Timedelta(days=59)
        s60 = s[s["sale_date"] >= start_60]
        full_days = pd.date_range(start_60, max_date, freq="D")

        for pid in prod_rows:
            p_sales = s60[s60["product_id"] == pid.id]
            if p_sales.empty:
                daily_sales_by_prod[pid.id] = pd.Series(0.0, index=full_days)
            else:
                d_series = p_sales.groupby("sale_date")["quantity"].sum().reindex(full_days, fill_value=0.0)
                daily_sales_by_prod[pid.id] = d_series

    lines = []
    do_not_reorder = []

    for p in prod_rows:
        stock = stock_by_prod.get(p.id, 0)
        expiries = exp_by_prod.get(p.id, [])
        nearest_exp = min(expiries) if expiries else None
        days_to_exp = (nearest_exp - ref_date).days if nearest_exp else None

        series = daily_sales_by_prod.get(p.id, pd.Series(0.0, index=range(60)))
        total_units_sold = float(series.sum())
        avg_daily = float(round(series.mean(), 2))
        std_daily = float(series.std(ddof=1)) if len(series) > 1 else 0.0
        doc = round(stock / avg_daily, 1) if avg_daily > 0 else None

        # Check do-not-reorder rules:
        if total_units_sold == 0:
            do_not_reorder.append({
                "product": p.name,
                "reason": "No sales in the last 60 days",
            })
            continue

        if doc is not None and doc > 90:
            do_not_reorder.append({
                "product": p.name,
                "reason": f"Already overstocked ({int(doc)} days of supply)",
            })
            continue

        if nearest_exp and days_to_exp is not None and days_to_exp <= 60:
            do_not_reorder.append({
                "product": p.name,
                "reason": f"Batch expiring soon ({nearest_exp.isoformat()})",
            })
            continue

        # Reorder formula
        target_stock = avg_daily * (lead_days + cover_days) + 1.65 * std_daily * math.sqrt(lead_days)
        suggested_qty = math.ceil(target_stock - stock)

        if suggested_qty > 0:
            line_cost = round(suggested_qty * p.unit_cost, 2)
            lines.append({
                "product": p.name,
                "manufacturer": p.manufacturer,
                "stock_on_hand": stock,
                "avg_daily": avg_daily,
                "days_of_cover": doc,
                "suggested_qty": suggested_qty,
                "unit_cost": round(p.unit_cost, 2),
                "line_cost": line_cost,
            })

    # Sort lines by manufacturer asc, then suggested_qty desc
    lines.sort(key=lambda x: (x["manufacturer"], -x["suggested_qty"]))

    # Group by manufacturer
    mfr_dict: dict[str, list[Any]] = {}
    for line in lines:
        mfr_dict.setdefault(line["manufacturer"], []).append(line)

    by_mfr = []
    for mfr, m_lines in mfr_dict.items():
        by_mfr.append({
            "manufacturer": mfr,
            "items": len(m_lines),
            "total_cost": round(sum(l["line_cost"] for l in m_lines), 2),
        })
    by_mfr.sort(key=lambda x: x["manufacturer"])

    total_cost = round(sum(l["line_cost"] for l in lines), 2)

    return {
        "lines": lines,
        "by_manufacturer": by_mfr,
        "total_cost": total_cost,
        "do_not_reorder": do_not_reorder,
    }


def refills(within_days: int = 5, include_names: bool = False) -> dict[str, Any]:
    """
    Identify chronic medication refill patterns for regular customers.
    Only closed days are used.
    """
    refill_categories = ["Chronic Care (Rx)"]
    last_closed = get_last_closed_date()
    if last_closed is None:
        return {
            "summary": {"due_soon": 0, "overdue": 0, "lapsed": 0, "customers_due_soon": 0},
            "rows": [],
        }

    s = sales_df()
    if s.empty:
        return {
            "summary": {"due_soon": 0, "overdue": 0, "lapsed": 0, "customers_due_soon": 0},
            "rows": [],
        }

    with engine.connect() as conn:
        inv_rows = conn.execute(text("SELECT product_id, SUM(stock_on_hand) AS s FROM inventory GROUP BY product_id")).fetchall()
        cust_rows = conn.execute(text("SELECT id, name, phone FROM customers")).fetchall()

    stock_map = {r.product_id: (r.s or 0) for r in inv_rows}
    cust_map = {r.id: {"name": r.name, "phone": r.phone} for r in cust_rows}

    # Exclude walk-in customer (id 1 or starts with Walk-in)
    filtered_s = s[
        (s["customer_id"] != 1) &
        (~s["customer"].str.startswith("Walk-in")) &
        (s["category"].isin(refill_categories))
    ]

    if filtered_s.empty:
        return {
            "summary": {"due_soon": 0, "overdue": 0, "lapsed": 0, "customers_due_soon": 0},
            "rows": [],
        }

    rows = []
    # Group by customer_id and product_id
    grouped = filtered_s.groupby(["customer_id", "product_id"])

    for (cid, pid), group in grouped:
        cid = int(cid)
        pid = int(pid)
        dates = sorted(group["sale_date"].dt.date.unique())
        if len(dates) < 3:
            continue

        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        median_gap = float(np.median(gaps))

        if not (25 <= median_gap <= 36):
            continue

        last_purchase = max(dates)
        expected_due = last_purchase + timedelta(days=int(round(median_gap)))
        days_overdue = int((last_closed - expected_due).days)

        if -within_days <= days_overdue <= 0:
            status = "due_soon"
        elif 1 <= days_overdue <= 60:
            status = "overdue"
        elif days_overdue > 60:
            status = "lapsed"
        else:
            continue

        p_name = str(group["product"].iloc[0])
        c_info = cust_map.get(cid, {"name": str(group["customer"].iloc[0]), "phone": None})
        in_stock = bool(stock_map.get(pid, 0) > 0)
        usual_qty = int(round(float(group["quantity"].median())))

        rows.append({
            "customer_id": cid,
            "customer": c_info["name"],
            "phone": c_info["phone"],
            "product": p_name,
            "last_purchase": last_purchase.isoformat(),
            "expected_due": expected_due.isoformat(),
            "days_overdue": days_overdue,
            "status": status,
            "in_stock": in_stock,
            "usual_quantity": usual_qty,
        })

    # Sort rows by status (due_soon -> overdue -> lapsed), then days_overdue asc
    status_order = {"due_soon": 1, "overdue": 2, "lapsed": 3}
    rows.sort(key=lambda r: (status_order.get(r["status"], 99), r["days_overdue"]))

    due_soon_count = sum(1 for r in rows if r["status"] == "due_soon")
    overdue_count = sum(1 for r in rows if r["status"] == "overdue")
    lapsed_count = sum(1 for r in rows if r["status"] == "lapsed")
    customers_due_soon = len({r["customer_id"] for r in rows if r["status"] == "due_soon"})

    return {
        "summary": {
            "due_soon": due_soon_count,
            "overdue": overdue_count,
            "lapsed": lapsed_count,
            "customers_due_soon": customers_due_soon,
        },
        "rows": rows,
    }


def refill_message(customer_id: int, include_names: bool = False) -> dict[str, Any]:
    """Generate a friendly WhatsApp message and click-to-chat URL for customer refill reminder."""
    with SessionLocal() as db:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            return {"text": "", "whatsapp_url": None}
        phone = customer.phone
        cust_name = customer.name.split()[0] if customer.name else "Customer"

    store_name = os.getenv("STORE_NAME", "our pharmacy")
    default_cc = os.getenv("DEFAULT_COUNTRY_CODE", "91")

    # Get customer's refills
    all_refills = refills(within_days=10)
    cust_refills = [r for r in all_refills["rows"] if r["customer_id"] == customer_id and r["status"] in ("due_soon", "overdue")]

    if not cust_refills:
        due_str = "soon"
        prod_str = "medications"
    else:
        earliest_due = datetime.strptime(cust_refills[0]["expected_due"], "%Y-%m-%d").date()
        due_str = earliest_due.strftime("%-d %b")
        prod_names = list(dict.fromkeys(r["product"] for r in cust_refills))
        prod_str = ", ".join(prod_names)

    if include_names and cust_refills:
        text = f"Hello {cust_name}, this is {store_name}. Your regular refill for {prod_str} is due around {due_str}. We have it in stock. Reply to confirm and we'll keep it ready."
    else:
        text = f"Hello {cust_name}, this is {store_name}. Your regular refill is due around {due_str}. We have it in stock. Reply to confirm and we'll keep it ready."

    whatsapp_url = None
    if phone:
        digits = "".join(ch for ch in str(phone) if ch.isdigit())
        if len(digits) == 10:
            digits = default_cc + digits
        whatsapp_url = f"https://wa.me/{digits}?text={quote(text)}"

    return {
        "text": text,
        "whatsapp_url": whatsapp_url,
    }


def day_summary(target_date: Optional[date] = None) -> dict[str, Any]:
    """
    Generate comprehensive end-of-day summary metrics and WhatsApp-ready text for a closed date.
    """
    last_closed = get_last_closed_date()
    if target_date is None:
        target_date = last_closed
    if target_date is None:
        raise ValueError("No closed days found in database")

    with SessionLocal() as db:
        dc = db.query(DayClose).filter(DayClose.date == target_date).first()
        if not dc:
            raise ValueError(f"Date {target_date.isoformat()} is not closed")

    s = sales_df()
    sw = s[s["sale_date"].dt.date == target_date]

    revenue = round(float(dc.revenue), 2)
    invoices = int(dc.invoices)
    aov = round(revenue / invoices, 2) if invoices > 0 else 0.0

    cogs = float(round(sw["cogs"].sum(), 2)) if not sw.empty else 0.0
    gross_profit = round(revenue - cogs, 2)
    margin_pct = round(gross_profit / revenue * 100, 2) if revenue > 0 else 0.0

    # vs_usual_pct: % diff vs average revenue of previous 4 closed days with same weekday
    with engine.connect() as conn:
        weekday_closes = conn.execute(text("""
            SELECT date, revenue FROM day_closes
            WHERE date < :cur_date
            ORDER BY date DESC
        """), {"cur_date": str(target_date)}).fetchall()

    same_weekday_revs = []
    for r in weekday_closes:
        d = r.date
        if isinstance(d, str):
            d = datetime.strptime(d, "%Y-%m-%d").date()
        elif isinstance(d, datetime):
            d = d.date()
        if d.weekday() == target_date.weekday():
            same_weekday_revs.append(float(r.revenue))
            if len(same_weekday_revs) == 4:
                break

    vs_usual_pct = None
    if len(same_weekday_revs) >= 2:
        usual_avg = sum(same_weekday_revs) / len(same_weekday_revs)
        if usual_avg > 0:
            vs_usual_pct = round((revenue - usual_avg) / usual_avg * 100, 1)

    # Top 3 products
    top_prods = []
    if not sw.empty:
        p_agg = sw.groupby("product").agg(
            units=("quantity", "sum"),
            revenue=("total_amount", "sum")
        ).reset_index().sort_values("revenue", ascending=False).head(3)
        for _, pr in p_agg.iterrows():
            top_prods.append({
                "product": pr["product"],
                "units": int(pr["units"]),
                "revenue": round(float(pr["revenue"]), 2),
            })

    # Top category
    top_cat = None
    if not sw.empty:
        top_cat = sw.groupby("category")["total_amount"].sum().idxmax()

    # Unusual check from anomaly detection
    anom_data = anomalies(days=0)
    target_str = target_date.isoformat()
    target_anom = next((x for x in anom_data["series"] if x["date"] == target_str), None)
    unusual = {
        "is_unusual": target_anom["is_anomaly"] if target_anom else False,
        "type": target_anom["type"] if (target_anom and target_anom["is_anomaly"]) else None,
    }

    # Low stock items (< 7 days of cover)
    inv_data = inventory_status()
    low_stock_items = [p["product"] for p in inv_data["products"] if p["days_of_cover"] is not None and p["days_of_cover"] < 7]
    low_stock = {
        "count": len(low_stock_items),
        "items": low_stock_items[:3],
    }

    # Refills due tomorrow
    next_day = target_date + timedelta(days=1)
    refills_data = refills(within_days=5)
    refills_due_tomorrow = sum(
        1 for r in refills_data["rows"]
        if r["status"] == "due_soon" and r["expected_due"] == next_day.isoformat()
    )

    # Format plain WhatsApp summary text with Indian digit grouping
    def _in_fmt(num: float) -> str:
        s = f"{int(round(num)):,}"
        return s

    day_name = target_date.strftime("%a")
    d_str = target_date.strftime("%-d %b %Y")
    vs_str = ""
    if vs_usual_pct is not None:
        direction = "above" if vs_usual_pct >= 0 else "below"
        vs_str = f" ({abs(vs_usual_pct):.0f}% {direction} a usual {day_name})"

    best_str = ", ".join(f"{p['product']} ({p['units']})" for p in top_prods) or "None"
    low_str = ", ".join(low_stock['items']) or "None"

    summary_text = (
        f"Daily summary, {day_name} {d_str}\n"
        f"Sales: ₹{_in_fmt(revenue)} from {invoices} bills{vs_str}\n"
        f"Gross profit: ₹{_in_fmt(gross_profit)} ({margin_pct}%)\n"
        f"Best sellers: {best_str}\n"
        f"Top category: {top_cat or 'N/A'}\n"
        f"Running low: {low_str} ({low_stock['count']} items)\n"
        f"Refills due tomorrow: {refills_due_tomorrow}"
    )

    return {
        "date": target_str,
        "revenue": revenue,
        "invoices": invoices,
        "aov": aov,
        "gross_profit": gross_profit,
        "margin_pct": margin_pct,
        "vs_usual_pct": vs_usual_pct,
        "top_products": top_prods,
        "top_category": top_cat,
        "unusual": unusual,
        "low_stock": low_stock,
        "refills_due_tomorrow": refills_due_tomorrow,
        "summary_text": summary_text,
    }


def day_summaries(limit: int = 14) -> list[dict[str, Any]]:
    """Return summary list of the most recent closed days."""
    with engine.connect() as conn:
        closes = conn.execute(text("""
            SELECT date, invoices, revenue FROM day_closes
            ORDER BY date DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()

    if not closes:
        return []

    res = []
    for r in closes:
        d = r.date
        if isinstance(d, str):
            d = datetime.strptime(d, "%Y-%m-%d").date()
        elif isinstance(d, datetime):
            d = d.date()
        try:
            s_obj = day_summary(d)
            res.append({
                "date": d.isoformat(),
                "revenue": s_obj["revenue"],
                "invoices": s_obj["invoices"],
                "vs_usual_pct": s_obj["vs_usual_pct"],
                "gross_profit": s_obj["gross_profit"],
                "margin_pct": s_obj["margin_pct"],
            })
        except Exception:
            res.append({
                "date": d.isoformat(),
                "revenue": round(float(r.revenue), 2),
                "invoices": int(r.invoices),
                "vs_usual_pct": None,
                "gross_profit": 0.0,
                "margin_pct": 0.0,
            })

    return res


def profit_leaks(days: int = 90) -> dict[str, Any]:
    """
    Identify profit leakage across discounts, brand margin gaps, low-margin bestsellers,
    and expired stock write-offs.
    """
    s = sales_df()
    sw = _filter_window(s, days)

    def _in_fmt(num: float) -> str:
        return f"{int(round(num)):,}"

    # 1. Discount Leakage
    discount_leakage: dict[str, Any] = {
        "lines": 0,
        "total_discount_given": 0.0,
        "avg_discount_pct": 0.0,
        "top_products": [],
        "below_cost": [],
        "below_cost_loss_total": 0.0,
        "headline": "No discount leakage detected in this period.",
        "what_to_do": "Check who gave these discounts and whether they were allowed.",
    }

    if not sw.empty:
        # Lines where sale.unit_price < product's list price
        disc_lines = sw[sw["unit_price"] < (sw["product_unit_price"] - 0.01)].copy()
        if not disc_lines.empty:
            disc_lines["diff"] = disc_lines["product_unit_price"] - disc_lines["unit_price"]
            disc_lines["discount_amt"] = disc_lines["quantity"] * disc_lines["diff"]
            disc_lines["disc_pct"] = (disc_lines["diff"] / disc_lines["product_unit_price"] * 100).clip(lower=0)

            tot_disc = round(float(disc_lines["discount_amt"].sum()), 2)
            avg_disc = round(float(disc_lines["disc_pct"].mean()), 1)

            top_p = (
                disc_lines.groupby("product")
                .agg(lines=("id", "count"), discount_given=("discount_amt", "sum"))
                .reset_index()
                .sort_values("discount_given", ascending=False)
                .head(5)
            )
            top_p_list = [
                {"product": r["product"], "lines": int(r["lines"]), "discount_given": round(float(r["discount_given"]), 2)}
                for _, r in top_p.iterrows()
            ]

            # Below cost sales
            below_cost_lines = sw[sw["unit_price"] < (sw["unit_cost"] - 0.01)].copy()
            below_cost_list = []
            below_cost_tot = 0.0
            if not below_cost_lines.empty:
                below_cost_lines["loss"] = below_cost_lines["quantity"] * (below_cost_lines["unit_cost"] - below_cost_lines["unit_price"])
                below_cost_tot = round(float(below_cost_lines["loss"].sum()), 2)
                bc_sorted = below_cost_lines.sort_values("sale_date", ascending=False).head(20)
                for _, r in bc_sorted.iterrows():
                    below_cost_list.append({
                        "sale_date": r["sale_date"].strftime("%Y-%m-%d"),
                        "invoice_id": r["invoice_id"],
                        "product": r["product"],
                        "quantity": int(r["quantity"]),
                        "sold_price": round(float(r["unit_price"]), 2),
                        "unit_cost": round(float(r["unit_cost"]), 2),
                        "loss": round(float(r["loss"]), 2),
                    })

            discount_leakage = {
                "lines": int(len(disc_lines)),
                "total_discount_given": tot_disc,
                "avg_discount_pct": avg_disc,
                "top_products": top_p_list,
                "below_cost": below_cost_list,
                "below_cost_loss_total": below_cost_tot,
                "headline": f"₹{_in_fmt(tot_disc)} given in discounts across {len(disc_lines)} sales lines, including ₹{_in_fmt(below_cost_tot)} sold below purchase cost.",
                "what_to_do": "Check who gave these discounts and whether they were allowed.",
            }

    # 2. Brand Margin Gaps
    brand_margin_gaps: dict[str, Any] = {
        "items": [],
        "headline": "No brand margin gaps identified.",
        "what_to_do": "Recommend higher-margin alternatives when customers do not specify a brand.",
    }
    brands_data = brands_comparison(days=days)
    gap_items = []
    total_est_extra_profit = 0.0

    for g in brands_data:
        brands = g["brands"]
        if len(brands) < 2:
            continue
        leader = next((b for b in brands if b["flag"] == "leader"), brands[0])
        leader_margin = leader["margin_pct"]
        leader_monthly_units = leader["units"] / 3.0  # 90-day window divided by 3

        for b in brands:
            if b["product"] == leader["product"]:
                continue
            # Brand earns >= 3 percentage points more margin and has < 15% unit share
            if b["margin_pct"] >= (leader_margin + 3.0) and b["share_pct"] < 15.0:
                # Estimate assuming 10% of leader's monthly units shift to this brand
                shifted_units = leader_monthly_units * 0.10
                # Profit per unit
                leader_unit_profit = (leader["revenue"] - (leader["units"] * (leader["revenue"] / leader["units"] if leader["units"] > 0 else 0) * (1 - leader_margin/100))) / leader["units"] if leader["units"] > 0 else 0.0
                # Using unit price and unit cost directly:
                with SessionLocal() as db:
                    p_brand = db.query(Product).filter(Product.id == b.get("product_id")).first()
                    p_leader = db.query(Product).filter(Product.name == leader["product"]).first()
                    if p_brand and p_leader:
                        b_unit_prof = p_brand.unit_price - p_brand.unit_cost
                        l_unit_prof = p_leader.unit_price - p_leader.unit_cost
                        diff_prof = max(0.0, b_unit_prof - l_unit_prof)
                        extra_profit = round(shifted_units * diff_prof, 2)
                    else:
                        extra_profit = 0.0

                total_est_extra_profit += extra_profit
                gap_items.append({
                    "product_group": g["product_group"],
                    "brand": b["product"],
                    "manufacturer": b["manufacturer"],
                    "share_pct": b["share_pct"],
                    "margin_pct": b["margin_pct"],
                    "leader": leader["product"],
                    "leader_margin_pct": leader_margin,
                    "est_extra_profit_per_month": extra_profit,
                })

    gap_items.sort(key=lambda x: x["est_extra_profit_per_month"], reverse=True)
    if gap_items:
        brand_margin_gaps = {
            "items": gap_items,
            "headline": f"Switching 10% of sales to higher-margin brands could add ~₹{_in_fmt(total_est_extra_profit)}/month in extra profit.",
            "what_to_do": "Recommend higher-margin alternatives when customers do not specify a brand.",
        }

    # 3. Low-Margin Bestsellers
    low_margin_bestsellers: dict[str, Any] = {
        "items": [],
        "headline": "No low-margin bestseller issues identified.",
        "what_to_do": "Review purchase terms or adjust selling prices on low-margin high-volume products.",
    }
    if not sw.empty:
        p_agg = (
            sw.groupby(["product", "category"])
            .agg(revenue=("total_amount", "sum"), cogs=("cogs", "sum"))
            .reset_index()
        )
        total_rev = p_agg["revenue"].sum()
        total_cogs = p_agg["cogs"].sum()
        overall_margin_pct = round((total_rev - total_cogs) / total_rev * 100, 2) if total_rev > 0 else 0.0

        p_agg["profit"] = p_agg["revenue"] - p_agg["cogs"]
        p_agg["margin_pct"] = (p_agg["profit"] / p_agg["revenue"] * 100).round(2)
        p_agg = p_agg.sort_values("revenue", ascending=False)

        top_20_count = max(1, math.ceil(len(p_agg) * 0.20))
        top_products_df = p_agg.head(top_20_count)

        # Margin is > 5 points below overall margin
        low_margin_df = top_products_df[top_products_df["margin_pct"] < (overall_margin_pct - 5.0)]
        lm_items = []
        for _, r in low_margin_df.iterrows():
            lm_items.append({
                "product": r["product"],
                "category": r["category"],
                "revenue": round(float(r["revenue"]), 2),
                "margin_pct": round(float(r["margin_pct"]), 2),
                "overall_margin_pct": overall_margin_pct,
                "diff_pct": round(overall_margin_pct - float(r["margin_pct"]), 2),
            })

        if lm_items:
            low_margin_bestsellers = {
                "items": lm_items,
                "headline": f"{len(lm_items)} best-selling products make significantly lower profit margins than your store average of {overall_margin_pct}%.",
                "what_to_do": "Review supplier purchase costs or consider modest price adjustments for these bestsellers.",
            }

    # 4. Expiry Write-offs
    expiry_writeoffs: dict[str, Any] = {
        "months": [],
        "headline": "No expired stock write-offs recorded in the last 12 months.",
        "what_to_do": "Order in smaller batches and track expiry dates before stock lapses.",
    }
    e = expenses_df()
    if not e.empty and not s.empty:
        latest_sale_date = s["sale_date"].max()
        start_12m = latest_sale_date - pd.DateOffset(months=12)
        e12 = e[(e["expense_date"] >= start_12m) & (e["category"].str.contains("Expire|Write-off", case=False, na=False))].copy()

        if not e12.empty:
            e12["month"] = e12["expense_date"].dt.strftime("%Y-%m")
            monthly_exp = e12.groupby("month")["amount"].sum()

            s12 = s[s["sale_date"] >= start_12m].copy()
            s12["month"] = s12["sale_date"].dt.strftime("%Y-%m")
            monthly_rev = s12.groupby("month")["total_amount"].sum().to_dict()

            med_amt = float(monthly_exp.median()) if not monthly_exp.empty else 0.0
            tot_exp_amt = float(monthly_exp.sum())

            exp_list = []
            for m_str, amt in monthly_exp.items():
                m_rev = monthly_rev.get(m_str, 0.0)
                pct = round(amt / m_rev * 100, 2) if m_rev > 0 else 0.0
                is_high = bool(amt > (2.0 * med_amt) and med_amt > 0)
                exp_list.append({
                    "month": m_str,
                    "amount": round(float(amt), 2),
                    "pct_of_revenue": pct,
                    "is_above_2x_median": is_high,
                })
            exp_list.sort(key=lambda x: x["month"], reverse=True)

            expiry_writeoffs = {
                "months": exp_list,
                "headline": f"₹{_in_fmt(tot_exp_amt)} written off due to expired stock over the last 12 months.",
                "what_to_do": "Order in smaller batches and monitor upcoming expiry dates closely.",
            }

    return {
        "discount_leakage": discount_leakage,
        "brand_margin_gaps": brand_margin_gaps,
        "low_margin_bestsellers": low_margin_bestsellers,
        "expiry_writeoffs": expiry_writeoffs,
    }


def basket_pairs(days: int = 90, min_count: int = 20, limit: int = 15) -> dict[str, Any]:
    """
    Market-basket analysis comparing product groups per invoice over closed sales.
    Filter pairs with both_count >= min_count and lift >= 1.5, sorted by lift desc.
    """
    min_count = max(1, min_count)
    limit = min(max(1, limit), 50)

    s = sales_df()
    if s.empty:
        return {"total_invoices": 0, "pairs": []}

    sw = _filter_window(s, days)
    if sw.empty:
        return {"total_invoices": 0, "pairs": []}

    total_invoices = int(sw["invoice_id"].nunique())
    if total_invoices < min_count:
        return {"total_invoices": total_invoices, "pairs": []}

    # Group products by product_group, counting each group once per invoice
    inv_group = sw[["invoice_id", "product_group"]].drop_duplicates()
    group_counts = inv_group["product_group"].value_counts().to_dict()

    # Pre-filter groups that appear in >= min_count invoices
    eligible_groups = {g for g, cnt in group_counts.items() if cnt >= min_count}
    if len(eligible_groups) < 2:
        return {"total_invoices": total_invoices, "pairs": []}

    filtered_inv_group = inv_group[inv_group["product_group"].isin(eligible_groups)]

    # Self-join on invoice_id where group_a < group_b
    merged = pd.merge(
        filtered_inv_group,
        filtered_inv_group,
        on="invoice_id",
        suffixes=("_a", "_b")
    )
    pairs_df = merged[merged["product_group_a"] < merged["product_group_b"]]

    if pairs_df.empty:
        return {"total_invoices": total_invoices, "pairs": []}

    pair_counts = (
        pairs_df.groupby(["product_group_a", "product_group_b"])
        .size()
        .reset_index(name="both_count")
    )
    pair_counts = pair_counts[pair_counts["both_count"] >= min_count]

    results = []
    for _, r in pair_counts.iterrows():
        ga = r["product_group_a"]
        gb = r["product_group_b"]
        both = int(r["both_count"])
        cnt_a = group_counts[ga]
        cnt_b = group_counts[gb]

        support = round(both / total_invoices, 4)
        conf_a_b = round(both / cnt_a, 4)
        conf_b_a = round(both / cnt_b, 4)
        lift = round(both / ((cnt_a * cnt_b) / total_invoices), 2)

        if lift < 1.5:
            continue

        if conf_a_b >= conf_b_a:
            pct = int(round(conf_a_b * 100))
            insight = f"{pct}% of invoices with {ga} also include {gb}, {lift}x more often than usual."
        else:
            pct = int(round(conf_b_a * 100))
            insight = f"{pct}% of invoices with {gb} also include {ga}, {lift}x more often than usual."

        results.append({
            "group_a": ga,
            "group_b": gb,
            "both_count": both,
            "support": support,
            "confidence_a_to_b": conf_a_b,
            "confidence_b_to_a": conf_b_a,
            "lift": lift,
            "insight": insight,
        })

    results.sort(key=lambda x: x["lift"], reverse=True)
    return {
        "total_invoices": total_invoices,
        "pairs": results[:limit],
    }


def basket_companions(product_group: str, limit: int = 3) -> list[dict[str, Any]]:
    """
    Find top companion product groups for a given product group ranked by confidence,
    along with each group's most-sold brand for quick-add billing.
    """
    pairs_res = basket_pairs(days=90, min_count=5, limit=50)
    target = product_group.strip().lower()

    companions = []
    for p in pairs_res["pairs"]:
        ga = p["group_a"]
        gb = p["group_b"]
        if ga.strip().lower() == target:
            companions.append({
                "companion_group": gb,
                "confidence": p["confidence_a_to_b"],
                "lift": p["lift"],
            })
        elif gb.strip().lower() == target:
            companions.append({
                "companion_group": ga,
                "confidence": p["confidence_b_to_a"],
                "lift": p["lift"],
            })

    companions.sort(key=lambda x: (x["confidence"], x["lift"]), reverse=True)
    top_comps = companions[:limit]

    # Resolve most-sold brand in each companion group
    s = sales_df()
    res = []
    for comp in top_comps:
        c_name = comp["companion_group"]
        top_prod = None
        if not s.empty:
            c_sales = s[s["product_group"].str.lower() == c_name.lower()]
            if not c_sales.empty:
                best_row = c_sales.groupby(["product_id", "product"])["quantity"].sum().reset_index().sort_values("quantity", ascending=False).iloc[0]
                top_prod = {
                    "product_id": int(best_row["product_id"]),
                    "product": best_row["product"],
                }

        if top_prod is None:
            # Fallback to product name from products table
            with SessionLocal() as db:
                p_item = db.query(Product).filter(Product.product_group == c_name).first()
                if p_item:
                    top_prod = {"product_id": p_item.id, "product": p_item.name}

        res.append({
            "product_group": c_name,
            "companion_product": top_prod["product"] if top_prod else c_name,
            "product_id": top_prod["product_id"] if top_prod else None,
            "confidence": comp["confidence"],
            "lift": comp["lift"],
        })

    return res
