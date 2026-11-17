import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from typing import Any, Optional
from pathlib import Path
from . import analytics as A


OWNER_EMAIL = os.getenv("OWNER_EMAIL", "owner@companybrain.local")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "Company Brain <digest@companybrain.local>")
APP_URL = os.getenv("APP_URL", "http://localhost:3000")


def generate_email_content(target_date: date) -> tuple[str, str, str]:
    """
    Generate subject, plain-text body, and HTML body for daily day-close email digest.
    """
    summary = A.day_summary(target_date)
    dt_str = target_date.strftime("%d %b %Y")
    rev = summary.get("revenue", 0.0)
    gp = summary.get("gross_profit", 0.0)
    margin = summary.get("margin_pct", 0.0)
    inv_count = summary.get("invoices", 0)
    aov = summary.get("aov", 0.0)
    vs_usual = summary.get("vs_usual_pct")
    top_prods = summary.get("top_products", [])
    top_cat = summary.get("top_category") or "General"
    low_stock = summary.get("low_stock", {})
    refills_tomorrow = summary.get("refills_due_tomorrow", 0)
    unusual = summary.get("unusual", {})

    vs_usual_text = ""
    if vs_usual is not None:
        sign = "+" if vs_usual > 0 else ""
        vs_usual_text = f"({sign}{vs_usual}% vs typical {target_date.strftime('%A')})"

    subject = f"📊 Day Closed Report - {dt_str} | Revenue: ₹{int(round(rev)):,} ({margin}% Margin)"

    # Plain text version
    top_prods_text = "\n".join(
        f"  • {p['product']}: {p['units']} units (₹{int(round(p['revenue'])):,})"
        for p in top_prods
    ) or "  • No sales recorded"

    plain_text = f"""Company Brain - Daily End-of-Day Business Report
Business Date: {dt_str}
==================================================

KEY METRICS:
• Gross Revenue: ₹{int(round(rev)):,} {vs_usual_text}
• Gross Profit:  ₹{int(round(gp)):,} ({margin}% Margin)
• Invoices:      {inv_count} orders (Avg Bill: ₹{int(round(aov)):,})
• Top Category:  {top_cat}

TOP 3 PRODUCTS TODAY:
{top_prods_text}

ACTION ITEMS & ALERTS:
• Low Stock Items (< 7 days cover): {low_stock.get('count', 0)} items ({', '.join(low_stock.get('items', [])[:3]) or 'None'})
• Chronic Medicine Refills Due Tomorrow: {refills_tomorrow} patients

Full dashboard & analytics: {APP_URL}
"""

    # HTML Version
    prods_html_rows = ""
    for p in top_prods:
        prods_html_rows += f"""
        <tr>
          <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; font-size: 13.5px; color: #1f2937;"><strong>{p['product']}</strong></td>
          <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; font-size: 13.5px; color: #4b5563; text-align: right;">{p['units']}</td>
          <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; font-size: 13.5px; color: #1e3a8a; text-align: right; font-weight: 600;">₹{int(round(p['revenue'])):,}</td>
        </tr>
        """
    if not prods_html_rows:
        prods_html_rows = "<tr><td colspan='3' style='padding: 12px; text-align: center; color: #9ca3af;'>No sales recorded today.</td></tr>"

    unusual_banner = ""
    if unusual.get("is_unusual"):
        u_type = unusual.get("type", "spike")
        exp = A.explain_anomaly(target_date)
        bg = "#fef3c7" if u_type == "spike" else "#fee2e2"
        border_c = "#f59e0b" if u_type == "spike" else "#ef4444"
        text_c = "#92400e" if u_type == "spike" else "#991b1b"
        unusual_banner = f"""
        <div style="margin: 16px 0; padding: 12px 16px; background-color: {bg}; border-left: 4px solid {border_c}; border-radius: 4px;">
          <strong style="color: {text_c}; font-size: 14px;">⚠️ Unusual {u_type.capitalize()} Detected:</strong>
          <p style="margin: 4px 0 0; color: {text_c}; font-size: 13px; line-height: 1.5;">{exp.get('explanation')}</p>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e5e7eb; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
    <!-- Header -->
    <div style="background-color: #1e3a8a; padding: 20px 24px; color: #ffffff;">
      <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #93c5fd; font-weight: 600;">Company Brain</div>
      <h1 style="margin: 4px 0 0; font-size: 20px; font-weight: 700;">Daily End-of-Day Business Report</h1>
      <p style="margin: 4px 0 0; font-size: 13px; color: #bfdbfe;">Closed register for {dt_str}</p>
    </div>

    <!-- Body -->
    <div style="padding: 24px;">
      {unusual_banner}

      <!-- Metric Cards Grid -->
      <table style="width: 100%; border-collapse: separate; border-spacing: 8px; margin-bottom: 16px;">
        <tr>
          <td style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px;">
            <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Gross Revenue</div>
            <div style="font-size: 20px; font-weight: 700; color: #1e3a8a; margin-top: 2px;">₹{int(round(rev)):,}</div>
            <div style="font-size: 11px; color: #059669; margin-top: 2px;">{vs_usual_text}</div>
          </td>
          <td style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px;">
            <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Gross Profit</div>
            <div style="font-size: 20px; font-weight: 700; color: #0f766e; margin-top: 2px;">₹{int(round(gp)):,}</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">Margin: {margin}%</div>
          </td>
        </tr>
        <tr>
          <td style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px;">
            <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Invoices Billed</div>
            <div style="font-size: 20px; font-weight: 700; color: #1f2937; margin-top: 2px;">{inv_count}</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">Avg Bill: ₹{int(round(aov)):,}</div>
          </td>
          <td style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px;">
            <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Top Category</div>
            <div style="font-size: 18px; font-weight: 700; color: #1f2937; margin-top: 2px;">{top_cat}</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">Highest sales share</div>
          </td>
        </tr>
      </table>

      <!-- Top Sellers Table -->
      <h3 style="font-size: 14px; font-weight: 700; color: #1f2937; margin: 18px 0 8px;">Top 3 Products Sold Today</h3>
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <thead>
          <tr style="background-color: #f1f5f9;">
            <th style="padding: 8px 12px; text-align: left; font-size: 11px; text-transform: uppercase; color: #475569;">Product</th>
            <th style="padding: 8px 12px; text-align: right; font-size: 11px; text-transform: uppercase; color: #475569;">Units</th>
            <th style="padding: 8px 12px; text-align: right; font-size: 11px; text-transform: uppercase; color: #475569;">Revenue</th>
          </tr>
        </thead>
        <tbody>
          {prods_html_rows}
        </tbody>
      </table>

      <!-- Action Items & Alerts -->
      <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px; margin-bottom: 20px;">
        <h4 style="margin: 0 0 8px; font-size: 13px; font-weight: 700; color: #1f2937;">📋 Action Items for Tomorrow:</h4>
        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #4b5563; line-height: 1.6;">
          <li><strong>Low Stock:</strong> {low_stock.get('count', 0)} items have under 7 days of supply ({', '.join(low_stock.get('items', [])[:3]) or 'All stock healthy'}).</li>
          <li><strong>Patient Refills:</strong> {refills_tomorrow} patient(s) due tomorrow for chronic refills.</li>
        </ul>
      </div>

      <!-- Button -->
      <div style="text-align: center; margin: 24px 0 12px;">
        <a href="{APP_URL}" style="display: inline-block; background-color: #1e3a8a; color: #ffffff; text-decoration: none; font-weight: 600; font-size: 14px; padding: 10px 22px; border-radius: 6px;">Open Full Dashboard →</a>
      </div>
    </div>

    <!-- Footer -->
    <div style="background-color: #f8fafc; border-top: 1px solid #e5e7eb; padding: 12px 24px; text-align: center; font-size: 11.5px; color: #9ca3af;">
      This automated digest was generated upon register close by Company Brain Business Intelligence.
    </div>
  </div>
</body>
</html>
"""
    return subject, plain_text, html


def send_daily_digest(target_date: date, recipient: Optional[str] = None) -> dict[str, Any]:
    """
    Dispatch daily email digest to store owner. If SMTP is not configured,
    writes the HTML output to backend/data/email_digests/ for instant local preview.
    """
    to_email = recipient or OWNER_EMAIL
    subject, plain_text, html_body = generate_email_content(target_date)

    # Always persist rendered digest for history and preview
    digests_dir = Path("data/email_digests")
    digests_dir.mkdir(parents=True, exist_ok=True)
    dt_str = target_date.strftime("%Y-%m-%d")
    preview_file = digests_dir / f"digest_{dt_str}.html"
    preview_file.write_text(html_body, encoding="utf-8")

    delivered = False
    mode = "preview_saved"
    error = None

    if SMTP_HOST:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_FROM
            msg["To"] = to_email

            part1 = MIMEText(plain_text, "plain", "utf-8")
            part2 = MIMEText(html_body, "html", "utf-8")
            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                if SMTP_USER and SMTP_PASS:
                    server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, [to_email], msg.as_string())
            delivered = True
            mode = "smtp"
        except Exception as e:
            error = str(e)
            mode = "smtp_failed_fallback_saved"

    return {
        "status": "ok",
        "date": dt_str,
        "recipient": to_email,
        "delivered": delivered,
        "mode": mode,
        "subject": subject,
        "preview_file": str(preview_file),
        "error": error,
    }

