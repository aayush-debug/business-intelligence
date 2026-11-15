# Company Brain

A complete, production-ready **Business Intelligence & Decision Platform** for small businesses. Built with **FastAPI**, **SQLAlchemy 2.0**, **Pandas**, and **Next.js 14** (App Router, React 18, Plain CSS).

Supports SQLite locally and PostgreSQL 16 in production.

---

## Important: Upgrading From Previous Database

> [!IMPORTANT]
> If you have an existing local SQLite database file (`backend/company_brain.db` or `backend/bi.db`), **delete it once** so that the updated schema (`inventory`, `day_closes`, `product_group`, `manufacturer`, `phone`, `sale_time`, `source`) is initialized cleanly:
> ```bash
> rm -f backend/company_brain.db backend/bi.db company_brain.db bi.db
> ```
> The server will start **completely empty**. You can load demo data at any time via `POST /api/demo/load` or upload your own files via the `/data` web interface.

---

## Tech Stack

**Backend**
- **Python 3.11+**
- **FastAPI**: Modern REST API framework
- **SQLAlchemy 2.0**: ORM and connection pooling
- **Pandas & NumPy**: In-memory data transformation, anomaly detection, forecasting
- **openpyxl**: Excel file parsing (.xlsx)
- **python-multipart**: Multipart form data parser for file uploads
- **SQLite** (local default) / **PostgreSQL 16** (production / docker-compose)

**Frontend**
- **Next.js 14** (App Router, configured for static HTML export `output: "export"`)
- **React 18** (Plain JavaScript, no TypeScript, client-rendered)
- **Recharts**: Responsive charting
- **Plain CSS**: Clean, dependency-free CSS in `globals.css` with Indian Rupee formatting (`₹`)

---

## Folder Structure

```text
company-brain/
  backend/
    app/
      __init__.py
      main.py          # FastAPI app, API routes, lifespan & CORS
      db.py            # Database engine, SessionLocal, and SQLAlchemy models
      analytics.py     # KPIs, trends, brands, inventory, refills, profit leaks, basket
      importer.py      # Multi-format data import, preview, column mapping, validation
      seed.py          # Demo CSV loader (triggered via POST /api/demo/load)
      chat.py          # BI Assistant tools and query fallback
    data/              # Seed CSV datasets
      products.csv
      customers.csv
      sales.csv
      expenses.csv
    requirements.txt   # Pinned dependencies
    Dockerfile         # Multi-stage Python container
  bi-platform/
    frontend/          # Next.js 14 application
      app/
        globals.css    # Clean, modern stylesheet
        layout.js      # App layout with sticky navigation
        nav.js         # Top navbar with status badge and open-days banner
        page.js        # Dashboard (KPIs, Charts, Brands, Stock, Leaks, Basket)
        billing/page.js# Point-of-Sale billing, companion chips, and Close Day modal
        data/page.js   # File upload wizard, preview, mapping & rejection summary
        reorder/page.js# Restock suggestions by manufacturer, CSV download, WhatsApp copy
        refills/page.js# Chronic care refill alerts, privacy toggle, WhatsApp link
        summary/page.js# 14-day closed history and WhatsApp daily report preview
      package.json
      next.config.js
      .env.example
  docker-compose.yml   # PostgreSQL 16 + backend with healthcheck
  README.md
```

---

## Database Models

- **Product (`products`)**: `id`, `name`, `category`, `unit_cost`, `unit_price`, `product_group` (indexed, nullable), `manufacturer` (nullable)
- **Customer (`customers`)**: `id`, `name`, `city`, `phone` (nullable)
- **Sale (`sales`)**: `id`, `invoice_id` (indexed), `sale_date` (Date, indexed), `sale_time` (DateTime, nullable), `customer_id` (FK), `product_id` (FK), `quantity`, `unit_price`, `total_amount`, `source` ("import" or "live")
- **Expense (`expenses`)**: `id`, `expense_date` (Date, indexed), `category`, `amount`
- **Inventory (`inventory`)**: `id`, `product_id` (FK), `batch_no`, `stock_on_hand`, `reorder_level`, `expiry_date` (Date, indexed), `last_restock_date` (Date) — unique constraint on `(product_id, batch_no)`
- **DayClose (`day_closes`)**: `date` (Date, PK), `closed_at` (DateTime), `invoices` (int), `revenue` (float)

---

## Getting Started

### 1. Run the Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
By default, the server connects to SQLite at `./company_brain.db` and starts **EMPTY**.

### 2. Run the Frontend

#### Local Development Server
```bash
cd bi-platform/frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

#### Static Export & Local Testing
The frontend is configured as a standalone static export (`output: "export"`, `trailingSlash: true`, `images: { unoptimized: true }`), meaning it does not require a Node.js server in production and can be served from any static host (Cloudflare Pages, Netlify, Vercel, AWS S3, GitHub Pages, Nginx).

> **Important**: The backend address is set via the `NEXT_PUBLIC_API_URL` environment variable (defaults to `http://localhost:8000`). Because this is a static site export, `NEXT_PUBLIC_API_URL` is **baked in at build time** into the client JavaScript bundles. If deploying to production, define `NEXT_PUBLIC_API_URL=https://your-api.com` prior to building.

To build the static export and test the exported site locally:
```bash
cd bi-platform/frontend
npm run build
npx serve out
```
This serves the generated static assets from the `out/` directory.

### 3. Load Demo Data (Optional)
To populate the database with the sample pharmacy dataset:
```bash
curl -X POST http://localhost:8000/api/demo/load
```

---

## API Reference

### Health, Stats & Seeding
- `GET /health`: Health status check.
- `GET /api/stats`: Table row counts.
- `GET /api/data/status`: Status of all 5 datasets (`{rows, loaded}`), date boundaries, and last closed date.
- `POST /api/demo/load`: Loads demo CSVs (returns `409` if database is not empty).

### Data Import System
- `GET /api/import/template/{dataset}`: Download a header-only CSV template for `products`, `customers`, `sales`, `expenses`, or `inventory`.
- `POST /api/import/preview`: Upload `.csv`, `.tsv`, `.txt`, `.xlsx`, or `.json` to preview columns, sample rows, and suggested mappings.
- `POST /api/import/commit`: Atomically insert rows with deduplication, currency stripping, and rejected rows logging.
- `GET /api/import/rejected/{filename}`: Download CSV of rejected invalid rows with exact reasons.

### Live Billing & Day Closes
- `POST /api/sales/live`: Create live invoice, decrement inventory batches FIFO by earliest expiry, mark as `source="live"`.
- `GET /api/day/status`: Check last closed date and list open days (counts only, no open revenue).
- `POST /api/day/close`: Chronologically close a day, calculate totals, update `day_closes`, and return closed day summary.
- `POST /api/day/close-due`: Automated cron endpoint closing all open days prior to today (requires `X-Cron-Secret`).

### Core & Advanced Analytics (Closed Days Only)
- `GET /api/kpis?days=90`: Revenue, net profit, margin %, orders, customer count, AOV, and growth vs previous window.
- `GET /api/trend?granularity=week&days=365`: Periodic revenue and gross profit series.
- `GET /api/top-products?days=90&limit=8`: Best-selling products by revenue and margin.
- `GET /api/categories?days=90`: Revenue and gross profit grouped by category.
- `GET /api/anomalies?days=180`: Weekday-normalized rolling z-score spike and drop detector.
- `GET /api/forecast?horizon=30`: 30-day projection with weekday seasonality and 28-day backtest.
- `GET /api/brands/comparison?days=90`: Competing brands analysis, unit market share, and plain-English insights.
- `GET /api/inventory/status`: Stock alerts (reorder, overstocked, expiring soon, dead stock) and tied-up capital.
- `GET /api/reorder/suggestions?lead_days=5&cover_days=14`: Recommended restock quantities grouped by manufacturer.
- `GET /api/reorder/export.csv`: Export purchase recommendations as CSV.
- `GET /api/refills?within_days=5`: Chronic prescription refill predictions (due soon, overdue, lapsed).
- `GET /api/refills/message`: Pre-composed WhatsApp reminder message and click-to-chat URL.
- `GET /api/day/summary?date=YYYY-MM-DD`: Day summary report with WhatsApp-ready formatted text.
- `GET /api/day/summaries?limit=14`: Recent closed days overview.
- `GET /api/profit/leaks?days=90`: Discount leakage, brand margin gaps, low-margin bestsellers, expiry write-offs.
- `GET /api/basket/pairs?days=90`: Market basket association rules (joint invoice count, support, confidence, lift).
- `GET /api/basket/companions?product_group=NAME`: Cross-sell companions for quick billing.
- `POST /api/chat`: AI Business Intelligence assistant with rule-based fallback and analytics tools.
