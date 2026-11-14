
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
  bi-platform/
    frontend/          # Next.js 14 dashboard (React 18, Recharts, Plain CSS)
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
