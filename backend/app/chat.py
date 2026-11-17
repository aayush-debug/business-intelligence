import os
import re
from typing import Any, Optional
from datetime import datetime, date
from sqlalchemy import text
from . import analytics as A
from . import snapshots as S
from .db import engine


STORE_TZ = os.getenv("STORE_TZ", "Asia/Kolkata")

SYSTEM_PROMPT = """You are the AI Business Intelligence Assistant for Company Brain.
You help small business owners understand their business numbers, sales, stock, and profits.

STRICT GUIDELINES:
1. Analytics cover CLOSED DAYS ONLY. Always state "data up to <last_closed_date>" when mentioning revenue, profit, or sales trends.
2. NEVER invent numbers. Use only data returned by the provided tools.
3. NEVER write SQL queries or discuss internal database tables.
4. Always present currency in Indian Rupees (₹) with standard Indian numbering (e.g., ₹1,25,000).
5. Keep your tone encouraging, clear, and business-practical.
"""

TOOLS = [
    {
        "name": "brand_comparison",
        "description": "Compare competing brands within product groups to identify imbalance, top sellers, and low-share brands.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Date window in days (default: 90)"}
            },
        },
    },
    {
        "name": "inventory_alerts",
        "description": "Get an overview of stock alerts including overstocked items, expiring soon, and items needing reorder.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "day_status",
        "description": "Check the last closed business date and whether any recent days are still open (unclosed).",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "kpis",
        "description": "Get key performance metrics: revenue, gross profit, expenses, net profit, margin, and order count.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Date window in days (default: 90, 0 for all time)"}
            },
        },
    },
    {
        "name": "top_products",
        "description": "Get top selling products ranked by revenue.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Date window in days (default: 90)"},
                "limit": {"type": "integer", "description": "Max products to return (default: 8)"}
            },
        },
    },
    {
        "name": "reorder_suggestions",
        "description": "Get purchase recommendations for products that are running low.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_days": {"type": "integer", "description": "Delivery time in days (default: 5)"},
                "cover_days": {"type": "integer", "description": "Days of stock to purchase (default: 14)"}
            },
        },
    },
    {
        "name": "profit_leaks",
        "description": "Find where profit is leaking through excessive discounts, below-cost sales, or expiry write-offs.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Date window in days (default: 90)"}
            },
        },
    },
]


def tool_brand_comparison(days: int = 90) -> list[dict[str, Any]]:
    if S.is_snapshot_mode():
        norm = S.normalize_days(days)
        groups = S.get_snapshot(f"brands_comparison__days-{norm}.json") or []
        return groups[:8]
    groups = A.brands_comparison(days=days)
    return groups[:8]


def tool_inventory_alerts() -> dict[str, Any]:
    if S.is_snapshot_mode():
        inv = S.get_snapshot("inventory_status.json") or {"summary": {}, "products": []}
    else:
        inv = A.inventory_status()
    summary = inv["summary"]
    products = inv["products"]

    # Filter top 10 items per status
    by_status: dict[str, list[Any]] = {}
    for p in products:
        by_status.setdefault(p["status"], []).append(p)

    categorized = {
        st: items[:10]
        for st, items in by_status.items()
    }
    return {
        "summary": summary,
        "alerts": categorized,
    }


def tool_day_status() -> dict[str, Any]:
    if S.is_snapshot_mode():
        snap = S.get_snapshot("day_status.json") or {}
        return {
            "last_closed_date": snap.get("last_closed_date"),
            "open_days_count": len(snap.get("open_days", [])),
            "open_days": [d["date"] for d in snap.get("open_days", [])],
            "today": snap.get("today", date.today().isoformat()),
        }

    last_closed = A.get_last_closed_date()
    today_dt = date.today()

    with engine.connect() as conn:
        closed_dates = set(r[0] for r in conn.execute(text("SELECT date FROM day_closes")).fetchall())
        sales_dates = set(r[0] for r in conn.execute(text("SELECT DISTINCT sale_date FROM sales")).fetchall())

    open_dates = sorted(list(sales_dates - closed_dates))

    return {
        "last_closed_date": last_closed.isoformat() if last_closed else None,
        "open_days_count": len(open_dates),
        "open_days": [d.isoformat() if hasattr(d, "isoformat") else str(d) for d in open_dates],
        "today": today_dt.isoformat(),
    }


def run_tool(name: str, args: dict[str, Any]) -> Any:
    """Execute tool by name with arguments."""
    if S.is_snapshot_mode():
        if name == "brand_comparison":
            return tool_brand_comparison(days=args.get("days", 90))
        elif name == "inventory_alerts":
            return tool_inventory_alerts()
        elif name == "day_status":
            return tool_day_status()
        elif name == "kpis":
            norm = S.normalize_days(args.get("days", 90))
            return S.get_snapshot(f"kpis__days-{norm}.json")
        elif name == "top_products":
            norm = S.normalize_days(args.get("days", 90))
            lim = args.get("limit", 8)
            res = S.get_snapshot(f"top_products__days-{norm}.json") or []
            return res[:lim]
        elif name == "reorder_suggestions":
            n_lead = S.normalize_lead_days(args.get("lead_days", 5))
            n_cover = S.normalize_cover_days(args.get("cover_days", 14))
            return S.get_snapshot(f"reorder_suggestions__lead_days-{n_lead}__cover_days-{n_cover}.json")
        elif name == "profit_leaks":
            norm = S.normalize_days(args.get("days", 90))
            return S.get_snapshot(f"profit_leaks__days-{norm}.json")
        else:
            return {"error": f"Unknown tool: {name}"}

    if name == "brand_comparison":
        return tool_brand_comparison(days=args.get("days", 90))
    elif name == "inventory_alerts":
        return tool_inventory_alerts()
    elif name == "day_status":
        return tool_day_status()
    elif name == "kpis":
        return A.kpis(days=args.get("days", 90))
    elif name == "top_products":
        return A.top_products(days=args.get("days", 90), limit=args.get("limit", 8))
    elif name == "reorder_suggestions":
        return A.reorder_suggestions(
            lead_days=args.get("lead_days", 5),
            cover_days=args.get("cover_days", 14)
        )
    elif name == "profit_leaks":
        return A.profit_leaks(days=args.get("days", 90))
    else:
        return {"error": f"Unknown tool: {name}"}


def parse_date_query(q: str) -> Optional[str]:
    """Extract a YYYY-MM-DD date from natural text like '13 Aug', '18th March 2026', '2026-03-18'."""
    # 1. Match YYYY-MM-DD
    m = re.search(r'(\d{4}-\d{2}-\d{2})', q)
    if m:
        return m.group(1)

    # 2. Match DD Mon (e.g. 18 Mar, 13 Aug, 18th March, 26 Jan 2026)
    m = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?', q)
    if m:
        day = int(m.group(1))
        mon_str = m.group(2)[:3].capitalize()
        year = int(m.group(3)) if m.group(3) else 2026
        try:
            dt = datetime.strptime(f"{day} {mon_str} {year}", "%d %b %Y").date()
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # 3. Match Mon DD (e.g. Aug 13, March 18th 2026)
    m = re.search(r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?', q)
    if m:
        mon_str = m.group(1)[:3].capitalize()
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else 2026
        try:
            dt = datetime.strptime(f"{day} {mon_str} {year}", "%d %b %Y").date()
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    return None


def rule_based_fallback(query: str) -> str:
    """Provide helpful answers when LLM API keys are not configured."""
    q = query.lower()

    if S.is_snapshot_mode():
        snap_status = S.get_snapshot("day_status.json") or {}
        last_closed_str = snap_status.get("last_closed_date")
        if last_closed_str:
            try:
                last_closed = datetime.strptime(last_closed_str, "%Y-%m-%d").date()
            except Exception:
                last_closed = None
        else:
            last_closed = None
    else:
        last_closed = A.get_last_closed_date()

    date_str = last_closed.strftime("%-d %b %Y") if last_closed else "No closed days"

    # Specific date anomaly / spike / drop explanation (e.g., "why was 13 Aug a spike?")
    if any(k in q for k in ["why", "explain", "reason", "cause", "what happened"]):
        matched_date = parse_date_query(q)
        if matched_date:
            if S.is_snapshot_mode():
                exp = S.get_snapshot(f"explain_anomaly__date-{matched_date}.json")
                if exp:
                    return exp["explanation"]
                return f"Data up to {date_str}: No specific anomaly analysis found for {matched_date} in the precomputed snapshot."
            exp = A.explain_anomaly(matched_date)
            return exp["explanation"]

    if any(k in q for k in ["hello", "hi", "hey", "help", "who are you", "what can you do"]):
        return (
            f"Hello! I am your Company Brain BI Assistant. My answers are strictly based on verified closed-day data "
            f"up to {date_str}. You can ask me about:\n"
            f"• Revenue, net profit & margins\n"
            f"• Inventory stock alerts & expiring batches\n"
            f"• Smart reorder recommendations\n"
            f"• Best selling products & catalog performance\n"
            f"• Competing brand comparisons\n"
            f"• 30-day sales forecast & unusual spikes/drops"
        )

    if any(k in q for k in ["top product", "best seller", "best selling", "top seller", "most sold"]):
        if S.is_snapshot_mode():
            top_p = S.get_snapshot("top_products__days-90.json") or []
        else:
            top_p = A.top_products(days=90, limit=5)
        if top_p:
            items_str = ", ".join(f"{p['product']} (₹{int(p['revenue']):,}, {p['units']} units, {p['margin_pct']}% margin)" for p in top_p[:3])
            return f"Data up to {date_str} (Last 90 days): Top selling products are: {items_str}."
        return f"Data up to {date_str}: No product sales recorded."

    if any(k in q for k in ["top customer", "best customer", "biggest customer", "most loyal", "client"]):
        if S.is_snapshot_mode():
            top_c = S.get_snapshot("top_customers__days-90.json") or []
        else:
            top_c = A.top_customers(days=90)
        if top_c:
            cust_str = ", ".join(f"{c['customer']} (₹{int(c['revenue']):,}, {c['orders']} orders)" for c in top_c[:3])
            return f"Data up to {date_str} (Last 90 days): Top customers by revenue are: {cust_str}."
        return f"Data up to {date_str}: No customer sales recorded."

    if any(k in q for k in ["forecast", "predict", "future", "next 30 days", "projection"]):
        if S.is_snapshot_mode():
            fc = S.get_snapshot("forecast__horizon-30.json") or S.get_snapshot("forecast.json") or {}
        else:
            fc = A.forecast()
        if fc:
            return (
                f"Based on historical sales up to {date_str}, projected revenue for the next 30 days is "
                f"₹{int(round(fc.get('total_forecast', 0))):,}. The forecast model improves on the naive baseline by "
                f"{fc.get('backtest', {}).get('improvement_pct', 0)}%."
            )
        return f"Data up to {date_str}: Forecast not available."

    if any(k in q for k in ["anomal", "unusual", "spike", "drop", "weird"]):
        if S.is_snapshot_mode():
            anom = S.get_snapshot("anomalies__days-90.json") or {}
        else:
            anom = A.anomalies(days=90)
        flagged = anom.get("flagged", [])
        if flagged:
            latest = flagged[0]
            return (
                f"Data up to {date_str}: {len(flagged)} unusual sales days detected in the last 90 days. "
                f"Most recent was {latest['date']}: ₹{int(round(latest['revenue'])):,} ({latest['type']})."
            )
        return f"Data up to {date_str}: No unusual revenue spikes or drops detected in the last 90 days."

    if any(k in q for k in ["refill", "chronic", "patient", "due"]):
        if S.is_snapshot_mode():
            ref = S.get_snapshot("refills.json") or {}
            items = ref.get("refills", [])
            return (
                f"Data up to {date_str}: {len(items)} patients are due or overdue for chronic medicine refills."
            )
        ref = A.refills(within_days=5, include_names=False)
        items = ref.get("refills", [])
        return (
            f"Data up to {date_str}: {len(items)} patients are due or overdue for chronic medicine refills."
        )

    if any(k in q for k in ["basket", "pair", "together", "cross sell", "companion"]):
        if S.is_snapshot_mode():
            mb = S.get_snapshot("basket_pairs__days-90.json") or {}
        else:
            mb = A.basket_pairs(days=90, min_count=20, limit=15)
        pairs = mb.get("pairs", [])
        if pairs:
            top_pair = pairs[0]
            return f"Data up to {date_str}: Strongest product pair is {top_pair['group_a']} + {top_pair['group_b']} ({top_pair['both_count']} joint bills, {top_pair['lift']}x lift). {top_pair.get('insight', '')}"
        return f"Data up to {date_str}: No strong product pairing patterns found yet."

    if any(k in q for k in ["brand", "compare"]):
        res = tool_brand_comparison(days=90)
        if not res:
            return f"Data up to {date_str}: No multi-brand product groups found in the catalog."
        top_group = res[0]
        return f"Data up to {date_str}: In '{top_group['product_group']}', {top_group.get('insight', '')}"

    if any(k in q for k in ["stock", "inventory", "alert", "expiry", "expiring", "overstock"]):
        alerts = tool_inventory_alerts()
        s = alerts["summary"]
        return (
            f"Data up to {date_str}: Inventory summary shows ₹{s.get('capital_tied_up_overstock', 0):,} tied up in overstocked items, "
            f"₹{s.get('value_expiring_soon', 0):,} in stock expiring within 60 days, and {s.get('items_to_reorder', 0)} items to reorder."
        )

    if any(k in q for k in ["reorder", "purchase", "order", "buy"]):
        if S.is_snapshot_mode():
            reord = S.get_snapshot("reorder_suggestions__lead_days-5__cover_days-14.json") or {}
        else:
            reord = A.reorder_suggestions(lead_days=5, cover_days=14)
        lines = reord.get("lines", [])
        if not lines:
            return f"Data up to {date_str}: All stock levels are sufficient based on current demand. No reorders needed."
        top3 = ", ".join(f"{l['product']} ({l['suggested_qty']} units)" for l in lines[:3])
        return f"Data up to {date_str}: Recommended reorders total ₹{reord.get('total_cost', 0):,}. Top items to order: {top3}."

    if any(k in q for k in ["day", "close", "status", "open"]):
        ds = tool_day_status()
        if ds["open_days_count"] > 0:
            return f"Last closed date: {ds['last_closed_date']}. There are {ds['open_days_count']} open day(s) waiting to be closed."
        return f"All days are closed up to {ds['last_closed_date']}."

    if any(k in q for k in ["leak", "discount", "loss", "profit gap"]):
        if S.is_snapshot_mode():
            pl = S.get_snapshot("profit_leaks__days-90.json") or {}
        else:
            pl = A.profit_leaks(days=90)
        return (
            f"Data up to {date_str}: {pl.get('discount_leakage', {}).get('headline', '')} "
            f"{pl.get('brand_margin_gaps', {}).get('headline', '')}"
        )

    # Default to KPIs
    if S.is_snapshot_mode():
        k = S.get_snapshot("kpis__days-90.json") or {}
    else:
        k = A.kpis(days=90)
    return (
        f"Data up to {date_str} (Last 90 days): Revenue is ₹{int(round(k.get('revenue', 0))):,}, "
        f"Gross profit is ₹{int(round(k.get('gross_profit', 0))):,}, and Net profit is ₹{int(round(k.get('net_profit', 0))):,} "
        f"({k.get('margin', 0)}% margin) across {k.get('orders', 0):,} orders."
    )


def handle_chat_message(message: str) -> dict[str, Any]:
    """Process user message and return assistant reply."""
    reply = rule_based_fallback(message)
    if S.is_snapshot_mode():
        ds = S.get_snapshot("day_status.json") or {}
        last_closed_str = ds.get("last_closed_date")
    else:
        last_closed = A.get_last_closed_date()
        last_closed_str = last_closed.isoformat() if last_closed else None
    return {
        "reply": reply,
        "last_closed_date": last_closed_str,
    }
