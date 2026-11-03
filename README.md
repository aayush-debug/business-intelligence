# Company Brain - Backend Foundation

A clean, production-ready backend foundation for **Company Brain**: a Business Intelligence and Decision Platform for small businesses. Built with FastAPI, SQLAlchemy 2.0, and Pandas. Supports SQLite for local development and PostgreSQL for production.

---

## Tech Stack

- **Python 3.11**
- **FastAPI**: Modern, fast web framework for building APIs
- **Uvicorn**: High-performance ASGI server
- **SQLAlchemy 2.0**: SQL toolkit and ORM
- **Pandas**: Fast CSV reading and data transformation
- **psycopg2-binary**: PostgreSQL adapter for Python
- **SQLite** (local default) / **PostgreSQL 16** (production / docker compose)

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
    data/              # Seed CSV datasets
      products.csv
      customers.csv
      sales.csv
      expenses.csv
    requirements.txt   # Pinned dependencies
    Dockerfile         # Multi-stage Python 3.11-slim container
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

---

## Seeding & Startup Behavior

1. **Table Creation**: Tables are automatically created if they do not exist.
2. **Conditional CSV Seeding**: If the `products` table is empty, the 4 CSV files in `backend/data/` are parsed and bulk-inserted into the database. If records already exist, seeding is skipped.
3. **Validation**: Each CSV file is validated against required columns; missing columns raise a descriptive error naming the file and the missing fields.
4. **Date Parsing**: Date columns (`sale_date` and `expense_date`) are converted to Python `datetime.date` objects.

---

## Local Setup & Run (venv + uvicorn)

### 1. Navigate to the backend directory
```bash
cd backend
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install pinned dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the API server with Uvicorn
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
By default, this connects to SQLite at `./company_brain.db`.

To point to a custom or PostgreSQL database locally:
```bash
export DATABASE_URL="postgresql://company_brain:company_brain@localhost:5432/company_brain"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Docker Compose Setup & Run

To run the full stack with PostgreSQL 16 and automatic healthchecks:

```bash
docker compose up --build
```

The database container boots first, validates its healthcheck (`pg_isready`), and then the backend container starts, runs migrations, seeds data, and listens on port 8000.

To run in the background (detached mode):
```bash
docker compose up --build -d
```

To stop services:
```bash
docker compose down
```

---

## API Verification

Once running, verify the backend endpoints:

### 1. Health Check
```bash
curl http://localhost:8000/health
```
**Response:**
```json
{"status": "ok"}
```

### 2. Stats Check
```bash
curl http://localhost:8000/api/stats
```
**Response:**
```json
{
  "products": 51,
  "customers": 420,
  "sales": 94652,
  "expenses": 176
}
```

### 3. Analytics Endpoints

- **KPIs**: `GET /api/kpis?days=90` (revenue, cogs, gross_profit, expenses, net_profit, margin, orders, customers, aov, revenue_growth, profit_growth, days)
- **Trends**: `GET /api/trend?granularity=week&days=365` (period, revenue, profit)
- **Top Products**: `GET /api/top-products?days=90&limit=8` (product, category, revenue, units, profit, margin_pct)
- **Top Customers**: `GET /api/top-customers?days=90&limit=8` (customer, revenue, orders — excludes walk-ins)
- **Categories**: `GET /api/categories?days=90` (category, revenue, profit)
- **Anomalies**: `GET /api/anomalies?days=180` (series and flagged spike/drop events via rolling z-scores on weekday-adjusted daily revenue)
- **Forecast**: `GET /api/forecast?horizon=30` (7-90 day trend projection with weekday seasonality, confidence bands, 60-day history, and 28-day backtest vs seasonal-naive baseline)


