#!/bin/bash

# Move to the root repository directory
cd "$(dirname "$0")"

echo ""
echo "  🧠 Starting Company Brain..."
echo "  --------------------------------------------------"

# 1. Free ports 8000 and 3000 if occupied
echo "  [1/4] Freeing ports 8000 and 3000..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
lsof -ti :3000 | xargs kill -9 2>/dev/null || true

# 2. Clear stale Next.js cache to avoid webpack module errors
echo "  [2/4] Cleaning build cache..."
rm -rf bi-platform/frontend/.next

# Create logs directory
mkdir -p logs

# 3. Start Backend
echo "  [3/4] Starting FastAPI Backend on port 8000..."
(cd backend && PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > ../logs/backend.log 2>&1) &
BACKEND_PID=$!

# 4. Start Frontend
echo "  [4/4] Starting Next.js Frontend on port 3000..."
(cd bi-platform/frontend && npm run dev > ../../logs/frontend.log 2>&1) &
FRONTEND_PID=$!

# Graceful cleanup on Ctrl+C or termination
cleanup() {
    echo ""
    echo "  Shutting down Company Brain..."
    kill -9 $BACKEND_PID 2>/dev/null || true
    kill -9 $FRONTEND_PID 2>/dev/null || true
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true
    lsof -ti :3000 | xargs kill -9 2>/dev/null || true
    echo "  ✓ All processes stopped cleanly."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for Backend and Frontend to be responsive
printf "  Waiting for servers to become ready..."
for i in {1..35}; do
    if curl -s http://localhost:8000/health >/dev/null 2>&1 && curl -s http://localhost:3000/ >/dev/null 2>&1; then
        break
    fi
    printf "."
    sleep 0.8
done
echo " Ready!"

# Terminal formatting
BOLD="\033[1m"
GREEN="\033[1;32m"
CYAN="\033[1;36m"
YELLOW="\033[1;33m"
RESET="\033[0m"

echo ""
echo -e "${GREEN}================================================================${RESET}"
echo -e "${BOLD}                🧠 COMPANY BRAIN IS READY!                     ${RESET}"
echo -e "${GREEN}================================================================${RESET}"
echo ""
echo -e "  ${BOLD}Click any link below to open in your browser:${RESET}"
echo ""
echo -e "  📊 ${BOLD}Business Dashboard:${RESET}   ${CYAN}http://localhost:3000${RESET}"
echo -e "  📂 ${BOLD}Upload / Import Data:${RESET} ${CYAN}http://localhost:3000/data/${RESET}"
echo -e "  💳 ${BOLD}POS Billing & Sales:${RESET}  ${CYAN}http://localhost:3000/billing/${RESET}"
echo -e "  🤖 ${BOLD}AI BI Chatbot:${RESET}        ${CYAN}http://localhost:3000/chat/${RESET}"
echo -e "  ⚡ ${BOLD}FastAPI Swagger Docs:${RESET} ${CYAN}http://localhost:8000/docs${RESET}"
echo ""
echo -e "  ${YELLOW}Logs are saved to:${RESET} logs/backend.log and logs/frontend.log"
echo -e "  ${YELLOW}To view live logs in another terminal:${RESET} tail -f logs/backend.log"
echo ""
echo -e "${GREEN}================================================================${RESET}"
echo -e "  ${BOLD}Press Ctrl+C in this terminal anytime to stop the servers.${RESET}"
echo -e "${GREEN}================================================================${RESET}"
echo ""

# Automatically open dashboard in browser on macOS
if command -v open >/dev/null 2>&1; then
    open "http://localhost:3000"
fi

# Wait for background processes
wait
