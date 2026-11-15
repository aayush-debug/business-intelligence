#!/bin/bash

# Move to the root repository directory
cd "$(dirname "$0")"

echo "=================================================="
echo "          🧠 Starting Company Brain...            "
echo "=================================================="

# 1. Free ports 8000 and 3000 if occupied
echo "--> Freeing ports 8000 and 3000..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
lsof -ti :3000 | xargs kill -9 2>/dev/null || true

# 2. Clear stale Next.js cache to avoid webpack module errors
rm -rf bi-platform/frontend/.next

# 3. Start Backend
echo "--> Starting FastAPI Backend on http://localhost:8000..."
(cd backend && PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
BACKEND_PID=$!

# Wait briefly for backend to initialize
sleep 1.5

# 4. Start Frontend
echo "--> Starting Next.js Frontend on http://localhost:3000..."
(cd bi-platform/frontend && npm run dev) &
FRONTEND_PID=$!

# Graceful cleanup on Ctrl+C or termination
cleanup() {
    echo ""
    echo "--> Shutting down Company Brain..."
    kill -9 $BACKEND_PID 2>/dev/null || true
    kill -9 $FRONTEND_PID 2>/dev/null || true
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true
    lsof -ti :3000 | xargs kill -9 2>/dev/null || true
    echo "✓ All processes stopped cleanly."
    exit 0
}
trap cleanup SIGINT SIGTERM

echo ""
echo "=================================================="
echo "  🚀 Company Brain is running!                    "
echo "  • Dashboard:   http://localhost:3000            "
echo "  • Upload Data: http://localhost:3000/data       "
echo "  • Backend API: http://localhost:8000/docs       "
echo "                                                  "
echo "  Press Ctrl+C anytime to stop both servers.      "
echo "=================================================="
echo ""

# Keep running and wait for background processes
wait
