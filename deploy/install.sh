#!/bin/bash
# Multiplayer Snake — install API + UDP relay on Ubuntu VPS
set -euo pipefail

APP_DIR=/opt/multiplayer-snake
REPO_URL="${REPO_URL:-https://github.com/sklionagrex-cpu/multiplayer-snake.git}"
API_PORT=8000
RELAY_PORT=40000

export DEBIAN_FRONTEND=noninteractive

echo "==> Fix apt repositories"
apt-get clean || true
apt-get update -y || true

# enable universe/multiverse if present
if [ -f /etc/apt/sources.list ]; then
  sed -i 's/^# deb /deb /g' /etc/apt/sources.list || true
fi
if [ -d /etc/apt/sources.list.d ]; then
  true
fi
apt-get update -y

echo "==> Install packages"
apt-get install -y python3 curl git ca-certificates openssl || true
apt-get install -y python3-pip || apt-get install -y python3-setuptools || true
apt-get install -y python3-venv || true
apt-get install -y ufw || true
apt-get install -y postgresql postgresql-contrib || apt-get install -y postgresql || true

echo "==> Python check"
python3 --version
# ensure pip
if ! python3 -m pip --version 2>/dev/null; then
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  python3 /tmp/get-pip.py || true
fi

echo "==> Database"
if command -v psql >/dev/null 2>&1 && systemctl start postgresql 2>/dev/null; then
  systemctl enable postgresql 2>/dev/null || true
  systemctl start postgresql || true
  sleep 2
  sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='snake'" 2>/dev/null | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER snake WITH PASSWORD 'snake_local_pass_change_me';" || true
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='snake'" 2>/dev/null | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE snake OWNER snake;" || true
  DB_URL="postgresql://snake:snake_local_pass_change_me@127.0.0.1:5432/snake"
else
  echo "Postgres not available — using SQLite"
  DB_URL="sqlite:////opt/multiplayer-snake/snake.db"
fi

echo "==> App directory"
mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/repo/.git" ]; then
  cd "$APP_DIR/repo" && git fetch --depth 1 origin main && git reset --hard origin/main
else
  rm -rf "$APP_DIR/repo"
  git clone --depth 1 -b main "$REPO_URL" "$APP_DIR/repo"
fi

echo "==> Python env"
cd "$APP_DIR"
if python3 -m venv "$APP_DIR/venv" 2>/dev/null; then
  PIP="$APP_DIR/venv/bin/pip"
  PY="$APP_DIR/venv/bin/python3"
  GUNI="$APP_DIR/venv/bin/gunicorn"
else
  PIP="python3 -m pip"
  PY="python3"
  GUNI="gunicorn"
  $PIP install -U pip || true
fi

$PIP install -U pip || true
$PIP install -r "$APP_DIR/repo/backend/requirements.txt"
# sqlite driver not needed for sqlalchemy default

SECRET=$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | xxd -p)
# If SQLite URL, patch main to accept sqlite — SQLAlchemy works with sqlite:///
# For pg8000 URL we need postgres; for sqlite use plain create_engine path in env
cat > "$APP_DIR/backend.env" << ENV
DATABASE_URL=$DB_URL
SECRET_KEY=$SECRET
ENV

# SQLAlchemy in main.py expects postgres-ish; for sqlite ensure URL works
# main.py uses pg8000 rewrite — skip for sqlite

echo "==> systemd snake-api"
if [ -x "$APP_DIR/venv/bin/gunicorn" ]; then
  EXEC="$APP_DIR/venv/bin/gunicorn main:app --bind 0.0.0.0:${API_PORT} --workers 1 --threads 4 --timeout 60"
else
  $PIP install gunicorn
  EXEC="$(command -v gunicorn) main:app --bind 0.0.0.0:${API_PORT} --workers 1 --threads 4 --timeout 60"
fi

cat > /etc/systemd/system/snake-api.service << UNIT
[Unit]
Description=Multiplayer Snake API
After=network.target

[Service]
WorkingDirectory=$APP_DIR/repo/backend
EnvironmentFile=$APP_DIR/backend.env
ExecStart=$EXEC
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

echo "==> systemd snake-relay"
cat > /etc/systemd/system/snake-relay.service << UNIT
[Unit]
Description=Multiplayer Snake UDP Relay
After=network.target

[Service]
WorkingDirectory=$APP_DIR/repo/relay
ExecStart=$PY $APP_DIR/repo/relay/relay_server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

if command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp || true
  ufw allow ${API_PORT}/tcp || true
  ufw allow ${RELAY_PORT}/udp || true
  ufw --force enable || true
fi

systemctl daemon-reload
systemctl enable --now snake-api snake-relay
sleep 2
systemctl --no-pager status snake-api || true
systemctl --no-pager status snake-relay || true

IP=$(curl -s4 --max-time 5 ifconfig.me 2>/dev/null || echo "109.120.152.78")
echo ""
echo "============================================"
echo " API:   http://${IP}:${API_PORT}/health"
echo " Relay: UDP ${IP}:${RELAY_PORT}"
echo "============================================"
curl -s "http://127.0.0.1:${API_PORT}/health" || true
echo ""
