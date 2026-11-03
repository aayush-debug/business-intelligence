from enum import Enum
import json
import time
from typing import Any, Optional
import pandas as pd
from sqlalchemy import text
from .db import engine


class Granularity(str, Enum):
    day = "day"
    week = "week"
    month = "month"


# In-memory DataFrame cache with TTL
_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _get_cached(key: str, loader_fn, ttl: float = 120.0) -> pd.DataFrame:
    now = time.time()
    if key in _cache:
        cached_time, cached_df = _cache[key]
        if now - cached_time < ttl:
            return cached_df.copy()
    df = loader_fn()
    _cache[key] = (now, df)
    return df.copy()


def clear_cache() -> None:
    """Clear in-memory cache (primarily for tests)."""
    _cache.clear()


def sales_df() -> pd.DataFrame:
    """Return sales joined with products and customers, with cogs computed. Cached for 120s."""
    def _load():
        sql = """
        SELECT s.invoice_id, s.sale_date, s.customer_id, s.product_id, s.quantity, s.total_amount,
               p.name AS product, p.category, p.unit_cost, c.name AS customer
        FROM sales s
        JOIN products p ON s.product_id = p.id
        JOIN customers c ON s.customer_id = c.id
        """
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, parse_dates=["sale_date"])
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
    """Each expense covers its calendar month; prorate by the number of days falling in [start, end]."""
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
    """Filter sales DataFrame for the window ending on latest sale_date. days=0 means all time."""
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

        # Previous window of equal length immediately preceding
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
        # All time: omit revenue_growth and profit_growth
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
        "week": "W-SUN",  # Weeks end on Sunday
        "month": "MS",    # Months start on the 1st
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
    # Exclude any customer whose name starts with "Walk-in"
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

