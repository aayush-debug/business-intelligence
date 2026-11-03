from enum import Enum
import json
import time
from typing import Any, Optional
import numpy as np
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

    # Weekday factor normalizes recurring weekly patterns (e.g. weekend peaks) so normal cyclical variation is not flagged
    overall_mean = d.mean() or 1.0
    factor = d.groupby(d.index.dayofweek).mean() / overall_mean
    adj = d / d.index.dayofweek.map(factor).values

    # Rolling statistics over the previous 28 days (shifted by 1 day to exclude current day)
    base = adj.shift(1).rolling(28, min_periods=14)
    base_mean = base.mean()
    base_std = base.std().replace(0, np.nan)
    z = (adj - base_mean) / base_std

    # Build series and classify anomalies
    df = pd.DataFrame({
        "date": d.index.strftime("%Y-%m-%d"),
        "revenue": d.values.round(2),
        "z": z.values.round(2),
    }).dropna()

    df["is_anomaly"] = (df["z"].abs() > 3).astype(bool)
    df["type"] = np.where(df["z"] > 0, "spike", "drop")

    # Filter window: days=0 means all available days
    if days > 0:
        df = df.tail(days)

    flagged = df[df["is_anomaly"]]

    return {
        "series": json.loads(df.to_json(orient="records")),
        "flagged": json.loads(flagged.to_json(orient="records")),
    }


def _fit_predict(train: pd.Series, dates: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Fit robust trend with weekday seasonality and predict future dates with confidence bands."""
    # 1. Weekday factor based on median revenue to account for day-of-week seasonality
    weekday_median = train.groupby(train.index.dayofweek).median()
    overall_median = train.median() or 1.0
    factor = weekday_median / overall_median

    # 2. Adjust revenue by weekday factor to isolate trend, using the last 84 days
    adj = train / train.index.dayofweek.map(factor).values
    adj_84 = adj.tail(84)
    med = adj_84.median()
    # Robust standard deviation estimator: 1.4826 * MAD
    mad = float((adj_84 - med).abs().median()) or 1.0
    # Outlier clipping: clip values beyond median +/- 3 * 1.4826 * MAD (~3 sigma) so one-off spikes do not skew trend
    adj_clipped = adj_84.clip(med - 3 * 1.4826 * mad, med + 3 * 1.4826 * mad)

    # 3. Fit a straight line (degree 1 polynomial) to the adjusted series
    x = np.arange(len(adj_clipped))
    slope, icpt = np.polyfit(x, adj_clipped.values, 1)
    resid = float(np.std(adj_clipped.values - (slope * x + icpt)))

    # 4. Project line values to future day indices and reapply each day's weekday factor
    xf = len(adj_clipped) + np.arange(len(dates))
    f = dates.dayofweek.map(factor).values
    mid = (slope * xf + icpt) * f
    band = 1.96 * resid * f
    return mid, band


def forecast(horizon: int = 30) -> dict[str, Any]:
    """Forecast future revenue using robust seasonal linear trend and evaluate backtest performance."""
    d = daily()
    if d.empty or len(d) < 35:
        return {
            "history": [],
            "forecast": [],
            "total_forecast": 0.0,
            "backtest": {"model_mae": 0.0, "naive_mae": 0.0, "improvement_pct": None},
        }

    # Clamp horizon to 7..90
    clamped_horizon = min(max(horizon, 7), 90)

    # BACKTEST: Hold out last 28 days, train on everything before
    hold = 28
    train, test = d.iloc[:-hold], d.iloc[-hold:]
    pred_mid, _ = _fit_predict(train, test.index)
    pred = np.clip(pred_mid, 0, None)

    # Seasonal-naive baseline: average of the last 4 same-weekday values in the training data
    naive = np.array([train[train.index.dayofweek == dw].tail(4).mean() for dw in test.index.dayofweek])
    mae_model = float(np.mean(np.abs(test.values - pred)))
    mae_naive = float(np.mean(np.abs(test.values - naive)))
    improvement_pct = round((1 - mae_model / mae_naive) * 100, 1) if mae_naive else None

    # FUTURE FORECAST
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

    # History: last 60 days
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


