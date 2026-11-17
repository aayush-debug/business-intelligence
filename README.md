# Company Brain

A complete, production-ready **Business Intelligence & Decision Platform** for small businesses and retail pharmacies. Built with **FastAPI**, **SQLAlchemy 2.0**, **Pandas**, and **Next.js 14** (App Router, React 18, Plain CSS).

Supports SQLite locally, PostgreSQL 16 in production, and a zero-database **Snapshot Mode** for instant demos.

---

## ⚡ Quick Start (One-Command Startup)

Run the entire platform (FastAPI Backend + Next.js Frontend) with a single command:

### 🍎 For Mac (Terminal)

Open your Terminal in the project folder and run:
```bash
./run.sh
```
- **What happens**:
  - Automatically frees ports `8000` & `3000`.
  - Clears stale `.next` cache to avoid webpack module errors.
  - Launches FastAPI backend (`:8000`) and Next.js frontend (`:3000`).
  - Displays high-visibility clickable links right inside your Terminal.
  - **Automatically opens `http://localhost:3000` in your default Mac browser (Safari / Chrome)**.
- **To stop**: Press `Ctrl + C` in the Terminal anytime to shut down both servers cleanly.

---

### 🪟 For Windows (Command Prompt, PowerShell, or Explorer)

#### Option 1: Command Prompt or PowerShell
Open Command Prompt (`cmd`) or PowerShell in the project folder and run:
```cmd
run.bat
```

#### Option 2: File Explorer Double-Click
Simply double-click the `run.bat` file in Windows File Explorer!

#### Option 3: Git Bash or WSL
If you use Git Bash or Windows Subsystem for Linux (WSL), run:
```bash
./run.sh
```

- **What happens**:
  - Automatically finds and terminates any stale processes on ports `8000` & `3000` using Windows `taskkill`.
  - Clears stale build cache and sets up log routing to `logs\`.
  - Launches both servers simultaneously.
  - Displays clickable URLs in the Windows console.
  - **Automatically opens `http://localhost:3000` in your default Windows browser (Edge / Chrome)**.
- **To stop**: Press `Ctrl + C` in the window anytime.

### Access Links
- **Business Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Data Import & Management**: [http://localhost:3000/data/](http://localhost:3000/data/)
- **Point-of-Sale (POS) Billing**: [http://localhost:3000/billing/](http://localhost:3000/billing/)
- **AI BI Assistant**: [http://localhost:3000/chat/](http://localhost:3000/chat/)
- **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### 🐳 Running with Docker (PostgreSQL 16 + FastAPI)

To run the backend containerized with a production PostgreSQL 16 database:

```bash
docker compose up -d
```

- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL Database**: `localhost:5432` (`company_brain` database)
- **Check Status**: `docker compose ps`
- **View Logs**: `docker compose logs -f backend`
- **Stop Services**: `docker compose down`

---

## 📊 Mock Data vs. Custom Business Data

Company Brain lets users seamlessly choose between testing with sample data or running their own store records:

1. **Option 1: Explore Mock Data**:
   - Pre-configured 2-year pharmacy dataset with **54 products**, **420 customers**, **94,677 sales**, **188 expenses**, and **53 inventory batches**.
   - Includes realistic chronic care refill cycles, brand margin comparisons, seasonal demand spikes, and anomaly alerts.
   - Load at any time via the UI banner on `/` and `/data`, or via `POST /api/demo/load?force=true`.

2. **Option 2: Upload Your Own Data**:
   - Import your business records for **Products**, **Sales**, **Stock / Inventory**, **Customers**, and **Expenses**.
   - Supports CSV, TSV, TXT, Excel (`.xlsx`), and JSON formats up to 20 MB.
   - Auto-detects columns, suggests mappings, detects duplicates, and exports invalid rows with human-readable error reasons.
   - Clear the database at any time via the **"Clear & upload own data"** button or `POST /api/data/reset`.

---

## 🛠️ Tech Stack

**Backend**
- **Python 3.11+**
- **FastAPI**: High-performance asynchronous REST API framework
- **SQLAlchemy 2.0**: Relational ORM with transactional savepoints and connection pooling
- **Pandas & NumPy**: Vectorized analytics, rolling z-score anomaly detection, 30-day Holt-Winters style forecasting
- **openpyxl**: Excel file parser (`.xlsx`)
- **python-multipart**: Multipart form data parser for streaming file uploads
- **SQLite** (local default) / **PostgreSQL 16** (production / docker-compose)

**Frontend**
- **Next.js 14** (App Router, static export `output: "export"`, `trailingSlash: true`)
- **React 18** (Plain JavaScript, client-rendered, no Node server required in production)
- **Recharts**: Responsive charts and graphs
- **Plain CSS**: Modern, design-tokenized stylesheet in `globals.css` with Indian Rupee formatting (`₹`)

---

## 📁 Repository Structure

```text
company-brain/
├── run.sh                     # One-command script to launch backend + frontend
├── docker-compose.yml         # PostgreSQL 16 + FastAPI production stack
├── README.md                  # System documentation
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI endpoints, CORS, lifespan & error handlers
│   │   ├── db.py              # Database engine, SessionLocal & SQLAlchemy models
│   │   ├── analytics.py       # KPIs, trends, brands, stock, refills, leaks & basket
│   │   ├── importer.py        # Robust file parser, savepoint isolation & auto-mapping
│   │   ├── seed.py            # Sample mock pharmacy dataset generator
│   │   ├── chat.py            # AI Business Assistant with analytics tool calling
│   │   ├── snapshots.py       # Snapshot loader and query normalizer for demo mode
│   │   ├── reports.py         # PDF and Excel accountant report generator
│   │   └── email_digest.py    # Daily business summary emailer
│   ├── data/                  # Sample CSV datasets
│   │   ├── products.csv
│   │   ├── customers.csv
│   │   ├── sales.csv
│   │   ├── expenses.csv
│   │   └── rejected/          # Automatically logged rejected rows CSVs
│   ├── snapshots/             # Precomputed JSON snapshots for zero-database deployment
│   │   ├── manifest.json      # Snapshot manifest, built timestamps & checksums
│   │   └── *.json             # Endpoint snapshot files (< 1 MB total)
│   ├── requirements.txt       # Python dependencies
│   └── Dockerfile             # Multi-stage production Docker container
├── bi-platform/
│   └── frontend/              # Next.js 14 frontend (static export ready)
│       ├── app/
│       │   ├── globals.css    # Clean typography & responsive layout styling
│       │   ├── layout.js      # Global layout wrapper
│       │   ├── nav.js         # Top navbar with mock data badge & day closing banner
│       │   ├── page.js        # Business Overview Dashboard
│       │   ├── billing/       # POS checkout with companion chips & Day Close modal
│       │   ├── chat/          # AI conversational business intelligence assistant
│       │   ├── data/          # File upload wizard, column mapping & data reset
│       │   ├── refills/       # Chronic care patient refill predictions & WhatsApp
│       │   ├── reorder/       # Restock suggestions by manufacturer & purchase export
│       │   └── summary/       # 14-day closed history and daily performance reports
│       ├── next.config.js     # Configured for static export (output: "export")
│       └── .env.example       # Example environment variables (NEXT_PUBLIC_API_URL)
└── scripts/
    ├── build_snapshots.py     # Generates precomputed snapshot JSONs from database
    └── check_snapshots.py     # Verification suite (live comparison, empty DB, memory check)
```

---

## 🗄️ Database Schema

- **Product (`products`)**: `id` (PK), `name`, `category`, `unit_cost`, `unit_price`, `product_group` (indexed), `manufacturer`
- **Customer (`customers`)**: `id` (PK), `name`, `city`, `phone`
- **Sale (`sales`)**: `id` (PK), `invoice_id` (indexed), `sale_date` (Date, indexed), `sale_time` (DateTime), `customer_id` (FK), `product_id` (FK), `quantity`, `unit_price`, `total_amount`, `source` (`"import"` or `"live"`)
- **Expense (`expenses`)**: `id` (PK), `expense_date` (Date, indexed), `category`, `amount`
- **Inventory (`inventory`)**: `id` (PK), `product_id` (FK), `batch_no`, `stock_on_hand`, `reorder_level`, `expiry_date` (Date, indexed), `last_restock_date` (Date) — unique on `(product_id, batch_no)`
- **DayClose (`day_closes`)**: `date` (Date, PK), `closed_at` (DateTime), `invoices` (int), `revenue` (float)

---

## 📥 Robust CSV & Excel Import Pipeline

The import engine in `backend/app/importer.py` features enterprise-grade safety:

1. **Transactional Savepoints (`with db.begin_nested():`)**:
   - Each row is committed inside an isolated savepoint.
   - If an individual row has an invalid date or negative price, only that row is rolled back and saved to the rejected file. The session is never poisoned, preventing `PendingRollbackError`.
2. **Primary Key Collision Protection**:
   - If a custom CSV has overlapping IDs (e.g. `product_id: 1` or `customer_id: 1`):
     - If the name matches an existing entry, it is cleanly recognized as a duplicate.
     - If the name is different, the conflicting ID is cleared and SQLite/Postgres auto-assigns the next unique primary key.
3. **Flexible Product & Customer Matching**:
   - Sales and inventory rows can match products and customers by integer ID, string ID (`"1"`), or exact/partial case-insensitive name.
4. **Auto-Calculations**:
   - `total_amount` in sales rows is automatically computed as `round(quantity * unit_price, 2)` if omitted in the source file.
5. **UTF-8 BOM Stripping**:
   - Handles Excel-exported CSV files containing byte-order marks (`\ufeff`) seamlessly.
6. **Downloadable Rejection Log**:
   - When any rows fail validation, a CSV is generated in `backend/data/rejected/` detailing the exact row number and explanation reason.

---

## 🚀 Deployment & Operational Modes

### Mode 1: Full Interactive Mode (Default)
Runs FastAPI with SQLite or PostgreSQL and live Next.js:
```bash
./run.sh
```

### Mode 2: Static Export (Frontend)
The frontend is deployable as a 100% static site to Cloudflare Pages, Vercel, Netlify, AWS S3, or Nginx:
```bash
cd bi-platform/frontend
npm run build
npx serve out
```
All routes are prerendered into `out/<route>/index.html`. API calls route to `process.env.NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).

### Mode 3: Zero-Database Snapshot Mode (`SNAPSHOT_MODE=true`)
Serve the entire demo directly from precomputed JSON files without connecting to or seeding any database:
- **Build Snapshots** (runs locally from database):
  ```bash
  python3 scripts/build_snapshots.py
  ```
- **Run Verification Suite**:
  ```bash
  python3 scripts/check_snapshots.py
  ```
  Tests 10 random snapshots against live calculations, runs 26 GET endpoints on an empty database, and asserts memory usage stays well under 200 MB (verified at ~170 MB).
- **Start in Snapshot Mode**:
  ```bash
  SNAPSHOT_MODE=true uvicorn app.main:app --port 8000
  ```

---

## 📡 API Reference

### System & Data Management
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Server health check (`{"status": "ok"}`) |
| `GET` | `/api/config` | Platform configuration (store name, demo mode, snapshot status) |
| `GET` | `/api/stats` | Database row counts across all tables |
| `GET` | `/api/data/status` | Dataset rows, date ranges, and `is_mock_data` flag |
| `POST` | `/api/demo/load` | Load sample mock dataset (pass `?force=true` to wipe and reload) |
| `POST` | `/api/data/reset` | Atomically wipe all tables to start clean with custom data |

### Data Import System
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/import/template/{dataset}` | Download header-only CSV template for products, sales, stock, etc. |
| `POST` | `/api/import/preview` | Upload file to inspect columns, preview rows, and get suggested mappings |
| `POST` | `/api/import/commit` | Atomically commit validated rows (`mode="append"` or `"replace"`) |
| `GET` | `/api/import/rejected/{filename}` | Download CSV of rejected invalid rows with failure reasons |

### Point of Sale & Day Closing
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/sales/live` | Create POS sale with FIFO inventory decrement; defaults to Walk-in Customer |
| `GET` | `/api/day/status` | Status of day closing and invoice counts for unclosed days |
| `POST` | `/api/day/close` | Chronologically close a business day, calculate totals, and update analytics |
| `POST` | `/api/day/close-due` | Automated cron endpoint to close past open days (requires `X-Cron-Secret`) |

### Business Analytics (Closed Days)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/kpis?days=90` | Revenue, gross profit, net profit, margin %, orders, AOV, and growth % |
| `GET` | `/api/trend?granularity=week&days=90` | Revenue and gross profit time-series (`day`, `week`, `month`) |
| `GET` | `/api/top-products?days=90&limit=8` | Top performing products sorted by revenue |
| `GET` | `/api/top-customers?days=90` | Customer frequency, spend, and chronic prescription tracking |
| `GET` | `/api/categories?days=90` | Category performance breakdown |
| `GET` | `/api/anomalies?days=90` | Rolling z-score spike and drop detector with plain-English reasons |
| `GET` | `/api/forecast?horizon=30` | 30-day demand projection with weekday seasonality and backtest |
| `GET` | `/api/brands/comparison?days=90` | Head-to-head brand comparison (e.g. Medora vs Curalife) |
| `GET` | `/api/inventory/status` | Stock status (reorder, overstocked, expiring soon, dead stock) |
| `GET` | `/api/reorder/suggestions` | Suggested purchase orders grouped by manufacturer |
| `GET` | `/api/reorder/export.csv` | Export purchase orders as CSV |
| `GET` | `/api/refills?within_days=5` | Chronic prescription refill alerts with WhatsApp contact link |
| `GET` | `/api/profit/leaks?days=90` | Discount leakage, margin gaps, low-margin bestsellers, write-offs |
| `GET` | `/api/basket/pairs?days=90` | Market basket association rules (joint orders, support, confidence, lift) |
| `GET` | `/api/basket/companions` | Cross-sell companion chips for rapid POS billing |
| `GET` | `/api/day/summary` | Daily summary performance card with WhatsApp formatted text |
| `GET` | `/api/day/summaries?limit=14` | Last 14 closed business day summaries |
| `POST` | `/api/chat` | AI Business Intelligence assistant with function tools and fallback |

---

## 📄 License
MIT License. Built for small business owners and retail operators.
