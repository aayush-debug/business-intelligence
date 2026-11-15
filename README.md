
# Company Brain

A Business Intelligence and Decision Platform for small businesses. It turns sales, expense and stock data into clear numbers: revenue and profit, best sellers, unusual days, a 30-day forecast, brand-versus-brand comparison and stock alerts, with an AI assistant on the roadmap.

The sample dataset is a mock medical store (pharmacy), but nothing in the platform is specific to pharmacies.

---

## Tech Stack

**Frontend**
- **Next.js 14** (App Router) with **React 18**, plain JavaScript
- **Recharts** for charts
- Plain CSS (no Tailwind, no UI library)

**Backend**
- **Python 3.11**
- **FastAPI**: web framework for the REST API
- **Uvicorn**: ASGI server
- **SQLAlchemy 2.0**: SQL toolkit and ORM
- **Pandas** and **NumPy**: data cleaning, KPIs, anomaly detection and forecasting
- **psycopg2-binary**: PostgreSQL adapter

**Database**
- **SQLite** for local development, **PostgreSQL 16** for production and Docker Compose

**AI (roadmap)**
- Anthropic Claude API with tool calling over the analytics functions (the model never writes SQL)

**Deployment (planned)**
- Render (backend + PostgreSQL) and Vercel (frontend); Docker Compose for local Postgres

---

## What it does

**Built**
- **Business overview dashboard**: revenue, net profit, profit margin, bills and average bill, with growth against the previous period; revenue and gross-profit trend (day, week or month); sales and profit by category; best-selling products with margin; date ranges of 30 days, 90 days, 1 year and all time
- **Unusual days**: spikes and drops in daily revenue, found with a weekday-adjusted rolling z-score
- **30-day forecast**: weekday seasonality plus a robust trend, with confidence bands and a 28-day backtest against a simple seasonal-naive baseline

**Planned** (see the roadmap below)
- Upload your own CSV, Excel or JSON files with column mapping and validation
- Brand comparison (for example, which of two competing brands sells less) and inventory alerts: reorder soon, overstocked, expiring soon
- Live billing during the day, with analytics shown only after the day is closed
- Reorder suggestions (a draft purchase list), daily summaries, profit-leak finder, "often bought together"
- AI assistant that answers questions from your numbers

**Scope decision**: the dashboard is about stock, buying and selling. Customer analytics (top customers, refill reminders) is intentionally left out of the interface. The `customers` table stays in the database because every sale references a customer, and the walk-in customer covers counter sales.

---

## Folder Structure

```text
company-brain/
  backend/
    app/
      __init__.py
      main.py          # FastAPI app, CORS configuration, startup & lifespan
      db.py            # Engine, SessionLocal, Base, and SQLAlchemy models
      seed.py          # CSV validation, date parsing, and bulk seeding logic
      analytics.py     # KPIs, trends, rankings, anomalies, forecasting
    data/              # Sample CSV dataset (mock pharmacy)
      products.csv
      customers.csv
      sales.csv
      expenses.csv
    requirements.txt   # Pinned dependencies
    Dockerfile         # Python 3.11-slim container
  bi-platform/
    frontend/          # Next.js 14 dashboard (React 18, Recharts, plain CSS)
      app/
        globals.css
        layout.js
        page.js
      package.json
      next.config.js
      .env.example
  docker-compose.yml   # PostgreSQL 16 + backend service with healthcheck
  .gitignore
  README.md
```

---

## Database Models

- **Product (`products`)**: `id`, `name`, `category`, `unit_cost`, `unit_price`
- **Customer (`customers`)**: `id`, `name`, `city`
- **Sale (`sales`)**: `id`, `invoice_id` (indexed), `sale_date` (Date, indexed), `customer_id` (FK -> `customers.id`, indexed), `product_id` (FK -> `products.id`, indexed), `quantity`, `unit_price`, `total_amount`
- **Expense (`expenses`)**: `id`, `expense_date` (Date, indexed), `category`, `amount`

Planned additions: `product_group` and `manufacturer` on products, an `inventory` table (stock on hand, reorder level, expiry date) and a `day_closes` table for end-of-day closing.

---

## Seeding & Startup Behavior

1. **Table creation**: tables are created automatically if they do not exist.
2. **Conditional CSV seeding**: if the `products` table is empty, the 4 CSV files in `backend/data/` are parsed and bulk-inserted. If records already exist, seeding is skipped, so restarting never duplicates data.
3. **Validation**: each CSV is checked against its required columns; a missing column raises an error naming the file and the missing fields.
4. **Date parsing**: `sale_date` and `expense_date` are converted to real dates.

This automatic loading is a stepping stone. The roadmap replaces it with user uploads, and keeps the sample data as an optional demo load.

---

## Local Setup & Run (venv + uvicorn)

### 1. Go to the backend directory
```bash
cd backend
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```
Use Python 3.11 or 3.12. Newer versions can fail to install the pinned packages.

### 3. Install pinned dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the API server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
By default this uses SQLite at `./company_brain.db` (created inside `backend/`). Interactive API docs are at `http://localhost:8000/docs`.

To use PostgreSQL locally:
```bash
export DATABASE_URL="postgresql://company_brain:company_brain@localhost:5432/company_brain"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Frontend Setup & Run (Next.js 14)

### 1. Go to the frontend directory
```bash
cd bi-platform/frontend
```

### 2. Configure the API address
```bash
cp .env.example .env.local
```
`NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`.

### 3. Install dependencies
```bash
npm install
```

### 4. Start the development server
```bash
npm run dev
```
The dashboard is at `http://localhost:3000`. Run `npm run build` to check that a production build passes.

---

## Docker Compose Setup & Run

Runs PostgreSQL 16 and the backend, with a database healthcheck:

```bash
docker compose up --build
```
The database starts first and passes its healthcheck (`pg_isready`), then the backend starts, creates the tables, seeds the data and listens on port 8000.

Run in the background: `docker compose up --build -d`. Stop: `docker compose down`.

---

## API Reference

All analytics endpoints take `days` (0 means all time). The window ends on the latest sale date in the data, not today.

### Health and stats
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/stats
```
`/health` returns `{"status": "ok"}`. `/api/stats` returns row counts, currently 51 products, 420 customers, 94,652 sales and 176 expenses for the sample data.

### Analytics endpoints
- **KPIs**: `GET /api/kpis?days=90`: revenue, cogs, gross_profit, expenses, net_profit, margin, orders, customers, aov, revenue_growth, profit_growth, days. Monthly expenses are spread across the days of each month, so profit is consistent across date ranges.
- **Trend**: `GET /api/trend?granularity=week&days=365`: period, revenue, profit
- **Top products**: `GET /api/top-products?days=90&limit=8`: product, category, revenue, units, profit, margin_pct
- **Categories**: `GET /api/categories?days=90`: category, revenue, profit
- **Anomalies**: `GET /api/anomalies?days=180`: the daily series plus flagged spikes and drops
- **Forecast**: `GET /api/forecast?horizon=30`: forecast with confidence bands, 60 days of history and the backtest against a seasonal-naive baseline
- **Top customers**: `GET /api/top-customers?days=90&limit=8`: still available, but the dashboard does not use it

---