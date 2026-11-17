import io
from datetime import datetime, timedelta
from typing import Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from . import analytics as A
from .db import SessionLocal, DayClose


def format_inr(num: float) -> str:
    """Format number as INR currency."""
    if num is None:
        return "₹0"
    return f"₹{int(round(num)):,}"


def get_report_data(days: int = 90) -> dict[str, Any]:
    """Gather comprehensive financial and audit data for accountant reports."""
    kpi_data = A.kpis(days=days)
    last_closed = A.get_last_closed_date()
    date_str = last_closed.strftime("%d %b %Y") if last_closed else "N/A"
    start_date = (last_closed - timedelta(days=days)) if (last_closed and days > 0) else None
    start_str = start_date.strftime("%d %b %Y") if start_date else "All Recorded History"

    # Monthly / Period P&L
    trend_monthly = A.trend(granularity="month", days=days)
    trend_daily = A.trend(granularity="day", days=days)

    # Product Sales Summary
    top_prods = A.top_products(days=days, limit=50)

    # Categories Summary
    cats = A.categories(days=days)

    # Inventory Valuation Summary
    inv = A.inventory_status()
    inv_summary = inv.get("summary", {})
    total_stock_value = sum(
        p.get("stock_value", 0.0) or 0.0 for p in inv.get("products", [])
    )

    # Itemized Expenses
    exp_df = A.expenses_df()
    if not exp_df.empty and start_date:
        exp_df = exp_df[exp_df["expense_date"].dt.date >= start_date]
        if last_closed:
            exp_df = exp_df[exp_df["expense_date"].dt.date <= last_closed]
    expenses_list = []
    if not exp_df.empty:
        for _, r in exp_df.sort_values("expense_date", ascending=False).iterrows():
            d_val = r["expense_date"]
            d_str = d_val.strftime("%Y-%m-%d") if hasattr(d_val, "strftime") else str(d_val)
            expenses_list.append({
                "date": d_str,
                "category": r["category"],
                "amount": float(r["amount"]),
            })

    # Day Closes Register
    with SessionLocal() as db:
        q = db.query(DayClose).order_by(DayClose.date.desc())
        if start_date:
            q = q.filter(DayClose.date >= start_date)
        if last_closed:
            q = q.filter(DayClose.date <= last_closed)
        closes = q.all()
        closes_list = [
            {
                "date": c.date.isoformat(),
                "closed_at": c.closed_at.strftime("%Y-%m-%d %H:%M:%S") if c.closed_at else "-",
                "invoices": c.invoices,
                "revenue": float(c.revenue),
            }
            for c in closes
        ]

    return {
        "period_label": f"{start_str} to {date_str}" if days > 0 else f"All time up to {date_str}",
        "days": days,
        "last_closed_date": date_str,
        "kpis": kpi_data,
        "trend_monthly": trend_monthly,
        "trend_daily": trend_daily,
        "products": top_prods,
        "categories": cats,
        "inventory": {
            "total_valuation": round(total_stock_value, 2),
            "capital_tied_up_overstock": inv_summary.get("capital_tied_up_overstock", 0),
            "value_expiring_soon": inv_summary.get("value_expiring_soon", 0),
            "items_to_reorder": inv_summary.get("items_to_reorder", 0),
        },
        "expenses": expenses_list,
        "day_closes": closes_list,
    }


def generate_accountant_excel(days: int = 90) -> bytes:
    """Generate multi-tab Excel workbook formatted for accountants."""
    data = get_report_data(days=days)
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styles
    navy_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    light_blue_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Calibri", size=16, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Calibri", size=10, italic=True, color="4B5563")
    bold_font = Font(name="Calibri", size=11, bold=True)
    regular_font = Font(name="Calibri", size=11)
    thin_border = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB"),
    )

    # --- Sheet 1: Executive P&L Summary ---
    ws1 = wb.create_sheet(title="P&L Summary")
    ws1.views.sheetView[0].showGridLines = True

    ws1.append(["COMPANY BRAIN — ACCOUNTANT FINANCIAL SUMMARY"])
    ws1["A1"].font = title_font
    ws1.append([f"Reporting Period: {data['period_label']}  |  Strictly Closed Business Days"])
    ws1["A2"].font = subtitle_font
    ws1.append([])

    kpis = data["kpis"]
    p_and_l = [
        ("Gross Sales / Revenue", kpis.get("revenue", 0.0)),
        ("Less: Cost of Goods Sold (COGS)", -kpis.get("cogs", 0.0)),
        ("Gross Profit", kpis.get("gross_profit", 0.0)),
        ("Less: Operating Expenses", -kpis.get("expenses", 0.0)),
        ("Net Operating Profit", kpis.get("net_profit", 0.0)),
    ]

    ws1.append(["Financial Metric", "Amount (INR)", "Margin / % of Revenue"])
    for col_idx in range(1, 4):
        cell = ws1.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = navy_fill
        cell.alignment = Alignment(horizontal="center" if col_idx > 1 else "left")

    row_num = 5
    rev = kpis.get("revenue", 0.0) or 1.0
    for name, amt in p_and_l:
        ws1.append([name, amt, f"{round(amt / rev * 100, 2)}%"])
        ws1.cell(row=row_num, column=1).font = bold_font if "Profit" in name or "Revenue" in name else regular_font
        ws1.cell(row=row_num, column=2).number_format = '"₹"#,##0.00'
        ws1.cell(row=row_num, column=2).alignment = Alignment(horizontal="right")
        ws1.cell(row=row_num, column=3).alignment = Alignment(horizontal="right")
        if "Gross Profit" in name or "Net Operating Profit" in name:
            ws1.cell(row=row_num, column=1).fill = light_blue_fill
            ws1.cell(row=row_num, column=2).fill = light_blue_fill
            ws1.cell(row=row_num, column=3).fill = light_blue_fill
        row_num += 1

    ws1.append([])
    ws1.append(["Operational Metrics", "Value"])
    h_row = row_num + 2
    for col_idx in (1, 2):
        c = ws1.cell(row=h_row, column=col_idx)
        c.font = header_font
        c.fill = navy_fill

    op_metrics = [
        ("Total Billed Invoices / Orders", kpis.get("orders", 0)),
        ("Unique Customers Served", kpis.get("customers", 0)),
        ("Average Order Value (AOV)", kpis.get("aov", 0.0)),
        ("Gross Margin Percentage", f"{kpis.get('margin', 0.0)}%"),
        ("Total Inventory Valuation (at cost)", data["inventory"]["total_valuation"]),
        ("Capital in Overstocked Items", data["inventory"]["capital_tied_up_overstock"]),
        ("Stock Expiring in 60 Days", data["inventory"]["value_expiring_soon"]),
    ]
    cur_r = h_row + 1
    for m_label, m_val in op_metrics:
        ws1.append([m_label, m_val])
        if isinstance(m_val, (int, float)) and "Total Billed" not in m_label and "Customers" not in m_label:
            ws1.cell(row=cur_r, column=2).number_format = '"₹"#,##0.00'
        ws1.cell(row=cur_r, column=2).alignment = Alignment(horizontal="right")
        cur_r += 1

    # --- Sheet 2: Monthly Breakdown ---
    ws2 = wb.create_sheet(title="Monthly Breakdown")
    ws2.views.sheetView[0].showGridLines = True
    ws2.append(["Month / Period", "Revenue", "Gross Profit", "Profit Margin %"])
    for col_idx in range(1, 5):
        c = ws2.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = navy_fill

    r_idx = 2
    for m in data["trend_monthly"]:
        rev_m = m.get("revenue", 0.0)
        prof_m = m.get("profit", 0.0)
        margin_m = f"{round(prof_m / rev_m * 100, 1)}%" if rev_m > 0 else "0.0%"
        ws2.append([m.get("period"), rev_m, prof_m, margin_m])
        ws2.cell(row=r_idx, column=2).number_format = '"₹"#,##0.00'
        ws2.cell(row=r_idx, column=3).number_format = '"₹"#,##0.00'
        ws2.cell(row=r_idx, column=2).alignment = Alignment(horizontal="right")
        ws2.cell(row=r_idx, column=3).alignment = Alignment(horizontal="right")
        ws2.cell(row=r_idx, column=4).alignment = Alignment(horizontal="right")
        r_idx += 1

    # --- Sheet 3: Product Sales ---
    ws3 = wb.create_sheet(title="Product Sales")
    ws3.views.sheetView[0].showGridLines = True
    ws3.append(["Product Name", "Category", "Units Sold", "Revenue", "Profit", "Margin %"])
    for col_idx in range(1, 7):
        c = ws3.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = navy_fill

    r_idx = 2
    for p in data["products"]:
        ws3.append([
            p.get("product"),
            p.get("category"),
            p.get("units"),
            p.get("revenue"),
            p.get("profit"),
            f"{p.get('margin_pct', 0.0)}%",
        ])
        ws3.cell(row=r_idx, column=3).alignment = Alignment(horizontal="right")
        ws3.cell(row=r_idx, column=4).number_format = '"₹"#,##0.00'
        ws3.cell(row=r_idx, column=4).alignment = Alignment(horizontal="right")
        ws3.cell(row=r_idx, column=5).number_format = '"₹"#,##0.00'
        ws3.cell(row=r_idx, column=5).alignment = Alignment(horizontal="right")
        ws3.cell(row=r_idx, column=6).alignment = Alignment(horizontal="right")
        r_idx += 1

    # --- Sheet 4: Operating Expenses ---
    ws4 = wb.create_sheet(title="Operating Expenses")
    ws4.views.sheetView[0].showGridLines = True
    ws4.append(["Date", "Category", "Amount"])
    for col_idx in range(1, 4):
        c = ws4.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = navy_fill

    r_idx = 2
    for exp in data["expenses"]:
        ws4.append([exp.get("date"), exp.get("category"), exp.get("amount")])
        ws4.cell(row=r_idx, column=3).number_format = '"₹"#,##0.00'
        ws4.cell(row=r_idx, column=3).alignment = Alignment(horizontal="right")
        r_idx += 1

    # --- Sheet 5: Day Closes Audit Register ---
    ws5 = wb.create_sheet(title="Day Closes Audit")
    ws5.views.sheetView[0].showGridLines = True
    ws5.append(["Business Date", "Closed At (UTC/Local)", "Invoices Billed", "Closed Revenue"])
    for col_idx in range(1, 5):
        c = ws5.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = navy_fill

    r_idx = 2
    for dc in data["day_closes"]:
        ws5.append([dc.get("date"), dc.get("closed_at"), dc.get("invoices"), dc.get("revenue")])
        ws5.cell(row=r_idx, column=3).alignment = Alignment(horizontal="right")
        ws5.cell(row=r_idx, column=4).number_format = '"₹"#,##0.00'
        ws5.cell(row=r_idx, column=4).alignment = Alignment(horizontal="right")
        r_idx += 1

    # Auto-adjust column widths across all sheets
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_accountant_pdf(days: int = 90) -> bytes:
    """Generate professional PDF Audit & Financial Report for accountant using ReportLab."""
    data = get_report_data(days=days)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1E3A8A"),
    )
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4B5563"),
    )
    section_h2 = ParagraphStyle(
        "SectionH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1F2937"),
        spaceBefore=14,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "CellNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#111827"),
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#111827"),
    )
    cell_right = ParagraphStyle(
        "CellRight",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=colors.HexColor("#111827"),
    )
    cell_right_bold = ParagraphStyle(
        "CellRightBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=colors.HexColor("#111827"),
    )

    story = []

    # Title & Header
    story.append(Paragraph("Company Brain — Financial Audit & Tax Report", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"<b>Reporting Period:</b> {data['period_label']} &nbsp;|&nbsp; "
        f"<b>Generated:</b> {datetime.now().strftime('%d %b %Y %H:%M')} &nbsp;|&nbsp; "
        f"<b>Status:</b> Strictly Closed Days",
        subtitle_style
    ))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceBefore=0, spaceAfter=12))

    # 1. Executive P&L Table
    k = data["kpis"]
    p_and_l_table_data = [
        [Paragraph("<b>Financial Metric</b>", cell_bold), Paragraph("<b>Amount (INR)</b>", cell_right_bold), Paragraph("<b>% of Revenue</b>", cell_right_bold)],
        [Paragraph("Gross Revenue / Sales", cell_bold), Paragraph(format_inr(k.get("revenue", 0)), cell_right_bold), Paragraph("100.0%", cell_right)],
        [Paragraph("Less: Cost of Goods Sold (COGS)", cell_style), Paragraph(format_inr(k.get("cogs", 0)), cell_right), Paragraph(f"{round((k.get('cogs', 0)/(k.get('revenue',1) or 1))*100, 1)}%", cell_right)],
        [Paragraph("<b>Gross Profit</b>", cell_bold), Paragraph(format_inr(k.get("gross_profit", 0)), cell_right_bold), Paragraph(f"{k.get('margin', 0)}%", cell_right_bold)],
        [Paragraph("Less: Operating Expenses", cell_style), Paragraph(format_inr(k.get("expenses", 0)), cell_right), Paragraph(f"{round((k.get('expenses', 0)/(k.get('revenue',1) or 1))*100, 1)}%", cell_right)],
        [Paragraph("<b>Net Operating Profit</b>", cell_bold), Paragraph(format_inr(k.get("net_profit", 0)), cell_right_bold), Paragraph(f"{round((k.get('net_profit', 0)/(k.get('revenue',1) or 1))*100, 1)}%", cell_right_bold)],
    ]
    t_pnl = Table(p_and_l_table_data, colWidths=[240, 140, 140])
    t_pnl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#F9FAFB")),
        ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#EEF2FF")),
    ]))
    story.append(Paragraph("1. Executive Profit & Loss Summary", section_h2))
    story.append(t_pnl)

    # 2. Operating & Inventory Summary
    inv = data["inventory"]
    op_table_data = [
        [Paragraph("<b>Operational Metric</b>", cell_bold), Paragraph("<b>Value</b>", cell_right_bold), Paragraph("<b>Inventory Status</b>", cell_bold), Paragraph("<b>Value (INR)</b>", cell_right_bold)],
        [Paragraph("Total Billed Invoices", cell_style), Paragraph(str(k.get("orders", 0)), cell_right), Paragraph("Total Stock Valuation (Cost)", cell_style), Paragraph(format_inr(inv.get("total_valuation", 0)), cell_right)],
        [Paragraph("Average Order Value (AOV)", cell_style), Paragraph(format_inr(k.get("aov", 0)), cell_right), Paragraph("Capital in Overstocked Stock", cell_style), Paragraph(format_inr(inv.get("capital_tied_up_overstock", 0)), cell_right)],
        [Paragraph("Unique Customers Served", cell_style), Paragraph(str(k.get("customers", 0)), cell_right), Paragraph("Stock Expiring in 60 Days", cell_style), Paragraph(format_inr(inv.get("value_expiring_soon", 0)), cell_right)],
    ]
    t_op = Table(op_table_data, colWidths=[140, 120, 140, 120])
    t_op.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
    ]))
    story.append(Paragraph("2. Operational Volume & Inventory Valuation", section_h2))
    story.append(t_op)

    # 3. Monthly Breakdown Table
    story.append(Paragraph("3. Monthly Financial Breakdown", section_h2))
    m_rows = [
        [Paragraph("<b>Month</b>", cell_bold), Paragraph("<b>Revenue</b>", cell_right_bold), Paragraph("<b>Gross Profit</b>", cell_right_bold), Paragraph("<b>Margin %</b>", cell_right_bold)]
    ]
    for m in data["trend_monthly"][:8]:
        r_val = m.get("revenue", 0)
        p_val = m.get("profit", 0)
        m_pct = f"{round(p_val / r_val * 100, 1)}%" if r_val > 0 else "0.0%"
        m_rows.append([
            Paragraph(m.get("period", "-"), cell_style),
            Paragraph(format_inr(r_val), cell_right),
            Paragraph(format_inr(p_val), cell_right),
            Paragraph(m_pct, cell_right),
        ])
    t_m = Table(m_rows, colWidths=[160, 120, 120, 120])
    t_m.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
    ]))
    story.append(t_m)

    # 4. Top Products Table
    story.append(Paragraph("4. Top Selling Products (by Revenue)", section_h2))
    p_rows = [
        [Paragraph("<b>Product</b>", cell_bold), Paragraph("<b>Category</b>", cell_bold), Paragraph("<b>Units</b>", cell_right_bold), Paragraph("<b>Revenue</b>", cell_right_bold), Paragraph("<b>Margin %</b>", cell_right_bold)]
    ]
    for p in data["products"][:6]:
        p_rows.append([
            Paragraph(p.get("product", "-"), cell_style),
            Paragraph(p.get("category", "-"), cell_style),
            Paragraph(str(p.get("units", 0)), cell_right),
            Paragraph(format_inr(p.get("revenue", 0)), cell_right),
            Paragraph(f"{p.get('margin_pct', 0.0)}%", cell_right),
        ])
    t_p = Table(p_rows, colWidths=[180, 120, 60, 90, 70])
    t_p.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
    ]))
    story.append(t_p)

    # 5. Sign-off Block
    story.append(Spacer(1, 14))
    sign_table_data = [
        [
            Paragraph("<b>Store Owner Verification:</b><br/><br/><br/>________________________<br/>Authorized Signatory", cell_style),
            Paragraph("<b>Accountant / Auditor Certification:</b><br/><br/><br/>________________________<br/>Chartered Accountant / Tax Auditor", cell_style),
        ]
    ]
    t_sign = Table(sign_table_data, colWidths=[260, 260])
    t_sign.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(KeepTogether([t_sign]))

    doc.build(story)
    return buf.getvalue()

