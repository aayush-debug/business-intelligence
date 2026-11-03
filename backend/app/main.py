import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import analytics as A
from .analytics import Granularity
from .db import Base, Customer, Expense, Product, Sale, engine, get_db
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables and seed CSV data if empty
    Base.metadata.create_all(bind=engine)
    seed_if_empty()
    yield


app = FastAPI(title="Company Brain", lifespan=lifespan)

# Parse CORS origins from FRONTEND_ORIGIN env var (default: "*")
raw_origins = os.getenv("FRONTEND_ORIGIN")
if raw_origins is None or not raw_origins.strip():
    origins = ["*"]
else:
    origins = [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True if "*" not in origins else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    """Return row counts for each database table to verify seeding."""
    return {
        "products": db.query(Product).count(),
        "customers": db.query(Customer).count(),
        "sales": db.query(Sale).count(),
        "expenses": db.query(Expense).count(),
    }


@app.get("/api/kpis")
def kpis(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Return key performance indicators for the specified window."""
    return A.kpis(days=days)


@app.get("/api/trend")
def trend(
    granularity: Granularity = Query(Granularity.week, description="Granularity (day, week, month)"),
    days: int = Query(365, ge=0, description="Date window in days (0 for all time)"),
):
    """Return periodic revenue and profit trends."""
    return A.trend(granularity=granularity.value, days=days)


@app.get("/api/top-products")
def top_products(
    days: int = Query(90, ge=0, description="Date window in days (0 for all time)"),
    limit: int = Query(8, ge=1, le=50, description="Max number of products to return"),
):
    """Return top products sorted by revenue descending."""
    return A.top_products(days=days, limit=limit)


@app.get("/api/top-customers")
def top_customers(
    days: int = Query(90, ge=0, description="Date window in days (0 for all time)"),
    limit: int = Query(8, ge=1, le=50, description="Max number of customers to return"),
):
    """Return top customers excluding walk-ins, sorted by revenue descending."""
    return A.top_customers(days=days, limit=limit)


@app.get("/api/categories")
def categories(days: int = Query(90, ge=0, description="Date window in days (0 for all time)")):
    """Return revenue and gross profit by category."""
    return A.categories(days=days)


@app.get("/api/anomalies")
def anomalies(days: int = Query(180, ge=0, description="Date window in days (0 for all time)")):
    """Detect daily revenue anomalies using weekday-normalized rolling z-scores."""
    return A.anomalies(days=days)


@app.get("/api/forecast")
def forecast(horizon: int = Query(30, description="Forecast horizon in days (clamped to 7..90)")):
    """Forecast future revenue with confidence bands and backtest metrics."""
    return A.forecast(horizon=min(max(horizon, 7), 90))



