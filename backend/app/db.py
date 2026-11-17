import os
from pathlib import Path
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker


def get_database_url() -> str:
    """Resolve database URL from environment, converting Postgres schemes to psycopg2."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        default_db = Path(__file__).resolve().parent.parent / "company_brain.db"
        url = f"sqlite:///{default_db}"
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


# Configure engine with SQLite thread-sharing support if using SQLite locally
database_url = get_database_url()
is_sqlite = database_url.startswith("sqlite")
engine_kwargs = {"pool_pre_ping": True}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    category = Column(String(100), nullable=False)
    unit_cost = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    # product_group: when null, treated as the product name
    product_group = Column(String(255), index=True, nullable=True)
    # manufacturer: when null, displayed as "Unknown"
    manufacturer = Column(String(255), nullable=True)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    city = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(String(50), nullable=False, index=True)
    sale_date = Column(Date, nullable=False, index=True)
    sale_time = Column(DateTime, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    # source: "import" or "live", default "import"
    source = Column(String(20), nullable=False, default="import")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    expense_date = Column(Date, nullable=False, index=True)
    category = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    batch_no = Column(String(100), nullable=True)
    stock_on_hand = Column(Integer, nullable=False, default=0)
    reorder_level = Column(Integer, nullable=True, default=0)
    expiry_date = Column(Date, nullable=True, index=True)
    last_restock_date = Column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("product_id", "batch_no", name="uq_product_batch"),
    )


class DayClose(Base):
    __tablename__ = "day_closes"

    date = Column(Date, primary_key=True)
    closed_at = Column(DateTime, nullable=False)
    invoices = Column(Integer, nullable=False)
    revenue = Column(Float, nullable=False)


def get_db():
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
