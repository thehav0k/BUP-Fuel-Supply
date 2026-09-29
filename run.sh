#!/usr/bin/env bash
# One command to run the whole platform.
#
#   ./run.sh            build (if needed) and start everything, wait until healthy, print URLs
#   ./run.sh demo       same, then reset the simulator and start the clock (SIMULATION_SPEED from .env)
#   ./run.sh e2e [N]    same, then run the end-to-end check for N ticks (default 200)
#   ./run.sh compare    same, then run the do-nothing vs platform comparison
#   ./run.sh verify     same, then inject every crisis, fault and fallback live and check the reaction
#   ./run.sh loadtest   same, then k6: 50 virtual users for 1 minute on /api/state and /api/recommendations
#   ./run.sh logs       follow backend logs
#   ./run.sh stop       stop everything (keeps data)
#   ./run.sh down       stop and remove everything including the database volume
set -euo pipefail
cd "$(dirname "$0")"

cmd="${1:-up}"
compose() { docker compose "$@"; }

ensure_docker() {
  if docker info >/dev/null 2>&1; then return; fi
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "Starting Docker Desktop..."
    open -a Docker
  fi
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && return; sleep 2; done
  echo "Docker is not running." >&2
  exit 1
}

ensure_env() {
  [[ -f .env ]] || { cp .env.example .env; echo "Created .env from .env.example"; }
}

up() {
  ensure_docker
  ensure_env
  set -a; . ./.env; set +a
  echo "Building and starting services (first run downloads images; later runs are cached)..."
  compose up -d --build --wait --wait-timeout 600
  compose ps --format 'table {{.Service}}\t{{.Status}}'
  cat <<EOF

  Dashboard    http://localhost:${FRONTEND_PORT:-3000}
  Backend API  http://localhost:8001/docs
  Grafana      http://localhost:3001  (admin/admin, dashboard "Fuel Supply Operations")
  Prometheus   http://localhost:9090
  Simulator    http://localhost:8000/admin

  The simulator starts paused. Use the dashboard's Demo tab, or: ./run.sh demo
EOF
}

case "$cmd" in
  up) up ;;
  demo)
    up
    curl -fsS -X POST localhost:8000/admin/reset >/dev/null
    curl -fsS -X POST localhost:8000/admin/run >/dev/null
    echo "Simulator reset and running."
    ;;
  e2e) up; python3 scripts/e2e.py --ticks "${2:-200}" ;;
  compare) up; (cd scripts && python3 compare.py --ticks "${2:-192}") ;;
  verify) up; python3 scripts/verify_live.py ;;
  loadtest)
    up
    docker run --rm -i --network bup-fuel-supply_default -e BASE_URL=http://backend:8001 grafana/k6:0.54.0 \
      run --summary-trend-stats "avg,med,p(95),p(99),max" - < loadtest/k6.js
    ;;
  logs) compose logs -f backend ;;
  stop) compose stop ;;
  down) compose down -v ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
