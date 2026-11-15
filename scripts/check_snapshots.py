#!/usr/bin/env python3
"""Verification tests for SNAPSHOT_MODE:
1. Compares 10 random snapshots against live database calculations.
2. Boots app with SNAPSHOT_MODE=true and an empty database, confirming every GET returns 200.
3. Reports memory usage while serving snapshots (confirming < 200 MB).
"""

from datetime import datetime
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
SNAPSHOTS_DIR = BACKEND_DIR / "snapshots"
DB_PATH = BACKEND_DIR / "company_brain.db"

sys.path.insert(0, str(BACKEND_DIR))


def assert_equal_values(live, snap, path=""):
    """Compare two data structures with float tolerance."""
    if isinstance(live, dict) and isinstance(snap, dict):
        for k in live:
            assert k in snap, f"Missing key {path}.{k} in snapshot"
            assert_equal_values(live[k], snap[k], f"{path}.{k}")
    elif isinstance(live, list) and isinstance(snap, list):
        assert len(live) == len(snap), f"Length mismatch at {path}: live={len(live)}, snap={len(snap)}"
        for idx, (l_item, s_item) in enumerate(zip(live, snap)):
            assert_equal_values(l_item, s_item, f"{path}[{idx}]")
    elif isinstance(live, (int, float)) and isinstance(snap, (int, float)):
        assert math.isclose(float(live), float(snap), rel_tol=1e-3, abs_tol=1e-2), (
            f"Value mismatch at {path}: live={live}, snap={snap}"
        )
    else:
        assert str(live) == str(snap), f"Mismatch at {path}: live={live}, snap={snap}"


def run_live_comparison():
    print("--- Test 1: Live Function Comparison for 10 Random Snapshots ---")
    os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    os.environ["SNAPSHOT_MODE"] = "false"

    from app import analytics as A

    manifest_path = SNAPSHOTS_DIR / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Filter candidate files that map directly to standard analytics functions
    candidates = [
        f for f in manifest["files"].keys()
        if f.endswith(".json") and not f.startswith("explain_") and not f.startswith("data_") and not f.startswith("stats") and not f.startswith("day_status")
    ]
    random.seed(42)
    selected_files = random.sample(candidates, 10)

    for fname in selected_files:
        snap_path = SNAPSHOTS_DIR / fname
        with open(snap_path, "r", encoding="utf-8") as f:
            snap_data = json.load(f)

        live_data = None
        if fname.startswith("kpis__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.kpis(days=d)
        elif fname.startswith("top_products__days-") or fname.startswith("top-products__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.top_products(days=d, limit=8)
        elif fname.startswith("top_customers__days-") or fname.startswith("top-customers__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.top_customers(days=d, limit=8)
        elif fname.startswith("categories__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.categories(days=d)
        elif fname.startswith("anomalies__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.anomalies(days=d)
        elif fname.startswith("brands_comparison__days-") or fname.startswith("brands-comparison__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.brands_comparison(days=d)
        elif fname.startswith("profit_leaks__days-") or fname.startswith("profit-leaks__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.profit_leaks(days=d)
        elif fname.startswith("basket_pairs__days-") or fname.startswith("basket-pairs__days-"):
            d = int(fname.split("days-")[1].replace(".json", ""))
            live_data = A.basket_pairs(days=d, min_count=20, limit=15)
        elif fname.startswith("trend__granularity-"):
            parts = fname.replace(".json", "").split("__")
            g = parts[1].split("-")[1]
            d = int(parts[2].split("-")[1])
            live_data = A.trend(granularity=g, days=d)
        elif fname.startswith("reorder_suggestions__lead_days-"):
            parts = fname.replace(".json", "").split("__")
            ld = int(parts[1].split("-")[1])
            cd = int(parts[2].split("-")[1])
            live_data = A.reorder_suggestions(lead_days=ld, cover_days=cd)
        elif fname.startswith("day_summary__date-"):
            dt_str = fname.split("date-")[1].replace(".json", "")
            live_data = A.day_summary(datetime.strptime(dt_str, "%Y-%m-%d").date())
        elif fname == "forecast__horizon-30.json" or fname == "forecast.json":
            live_data = A.forecast(horizon=30)
        elif fname == "inventory_status.json":
            live_data = A.inventory_status()
        elif fname == "day_summaries__limit-14.json" or fname == "day_summaries.json":
            live_data = A.day_summaries(limit=14)

        if live_data is not None:
            assert_equal_values(live_data, snap_data, path=fname)
            print(f"  ✓ {fname}: live calculation matches snapshot perfectly")


def run_serving_and_memory_test():
    print("\n--- Test 2: Serving in SNAPSHOT_MODE with EMPTY Database & Memory Check ---")
    runner_code = """
import os, resource, sys
os.environ['SNAPSHOT_MODE'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
endpoints = [
    '/health', '/api/config', '/api/stats', '/api/data/status', '/api/day/status',
    '/api/kpis?days=30', '/api/kpis?days=90', '/api/kpis?days=365', '/api/kpis?days=0',
    '/api/trend?granularity=day&days=30', '/api/trend?granularity=week&days=90', '/api/trend?granularity=month&days=365',
    '/api/top-products?days=90', '/api/top-customers?days=90', '/api/categories?days=90',
    '/api/anomalies?days=90', '/api/forecast?horizon=30', '/api/brands/comparison?days=90',
    '/api/inventory/status', '/api/reorder/suggestions?lead_days=5&cover_days=14', '/api/reorder/export.csv',
    '/api/day/summaries?limit=14', '/api/day/summary', '/api/profit/leaks?days=90', '/api/basket/pairs?days=90',
    '/api/refills?within_days=5'
]
for ep in endpoints:
    res = client.get(ep)
    assert res.status_code == 200, f"Endpoint {ep} failed: {res.status_code}"
    if 'export.csv' in ep:
        assert len(res.text) > 0
    else:
        assert res.json() is not None
    print(f'  ✓ GET {ep} -> 200 OK')

# Chat test
chat_res = client.post('/api/chat', json={'message': 'What was my revenue over the last 90 days?'})
assert chat_res.status_code == 200
chat_data = chat_res.json()
assert 'reply' in chat_data and len(chat_data['reply']) > 0
print(f"  ✓ POST /api/chat -> 200 OK (Reply: {chat_data['reply'][:50]}...)")

# Block write test
write_res = client.post('/api/sales/live', json={'customer_id': 1, 'items': [{'product_id': 1, 'quantity': 1}]})
assert write_res.status_code == 403
print('  ✓ POST /api/sales/live -> 403 Forbidden (Write blocked in snapshot mode)')

# Missing snapshot 404 test
missing_res = client.get('/api/day/summary?date=1999-01-01')
assert missing_res.status_code == 404
print('  ✓ GET /api/day/summary?date=1999-01-01 -> 404 Not Found')

# Memory check
rusage = resource.getrusage(resource.RUSAGE_SELF)
max_rss = rusage.ru_maxrss
max_rss_mb = round(max_rss / (1024 * 1024) if sys.platform == 'darwin' else max_rss / 1024, 2)
print(f'\\n--- Test 3: Memory Usage Report ---')
print(f'  Serving Process Max RSS Memory: {max_rss_mb} MB')
assert max_rss_mb < 200.0, f"Memory usage {max_rss_mb} MB exceeded 200 MB limit!"
print('  ✓ Memory usage is well under the 200 MB limit.')
"""
    res = subprocess.run([sys.executable, "-c", runner_code], cwd=str(BACKEND_DIR), capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print("ERROR:", res.stderr)
        raise RuntimeError("Serving test failed")


if __name__ == "__main__":
    manifest_file = SNAPSHOTS_DIR / "manifest.json"
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            m = json.load(f)
        print(f"Snapshot Manifest: {m.get('file_count')} files, {m.get('total_size_mb')} MB ({m.get('total_size_bytes'):,} bytes)")
        print(f"Built at: {m.get('snapshot_built_at')}\n")

    run_live_comparison()
    run_serving_and_memory_test()
    print("\n✓ All snapshot verification checks passed successfully!")
