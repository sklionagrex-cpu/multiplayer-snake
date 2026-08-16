#!/bin/bash
# Multiplayer Snake — install API + UDP relay on Ubuntu VPS
set -euo pipefail

APP_DIR=/opt/multiplayer-snake
REPO_URL="${REPO_URL:-https://github.com/sklionagrex-cpu/multiplayer-snake.git}"
API_PORT=8000
RELAY_PORT=40000

echo "==> Install packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git ufw postgresql postgresql-contrib curl

echo "==> PostgreSQL"
systemctl enable --now postgresql
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='snake'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER snake WITH PASSWORD 'snake_local_pass_change_me';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='snake'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE snake OWNER snake;"

echo "==> App directory"
mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/repo/.git" ]; then
  cd "$APP_DIR/repo" && git fetch --depth 1 origin main && git reset --hard origin/main
else
  rm -rf "$APP_DIR/repo"
  git clone --depth 1 -b main "$REPO_URL" "$APP_DIR/repo"
fi

echo "==> Python venv + backend deps"
python3 -m venv "$APP_DIR/venv"
# shellcheck disable=SC1091
source "$APP_DIR/venv/bin/activate"
pip install -q -U pip
pip install -q -r "$APP_DIR/repo/backend/requirements.txt"

SECRET=$(openssl rand -hex 24)
cat > "$APP_DIR/backend.env" << ENV
DATABASE_URL=postgresql://snake:snake_local_pass_change_me@127.0.0.1:5432/snake
SECRET_KEY=$SECRET
ENV

echo "==> systemd: snake-api"
cat > /etc/systemd/system/snake-api.service << UNIT
[Unit]
Description=Multiplayer Snake API
After=network.target postgresql.service

[Service]
WorkingDirectory=$APP_DIR/repo/backend
EnvironmentFile=$APP_DIR/backend.env
ExecStart=$APP_DIR/venv/bin/gunicorn main:app --bind 0.0.0.0:${API_PORT} --workers 1 --threads 4 --timeout 60
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
UNIT

echo "==> systemd: snake-relay"
cat > /etc/systemd/system/snake-relay.service << UNIT
[Unit]
Description=Multiplayer Snake UDP Relay
After=network.target

[Service]
WorkingDirectory=$APP_DIR/repo/relay
ExecStart=$APP_DIR/venv/bin/python3 $APP_DIR/repo/relay/relay_server.py
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
UNIT

echo "==> Firewall"
ufw allow 22/tcp || true
ufw allow ${API_PORT}/tcp || true
ufw allow ${RELAY_PORT}/udp || true
ufw --force enable || true

systemctl daemon-reload
systemctl enable --now snake-api snake-relay
sleep 2
systemctl --no-pager --full status snake-api || true
systemctl --no-pager --full status snake-relay || true

IP=$(curl -s4 ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "============================================"
echo " API:   http://${IP}:${API_PORT}/health"
echo " Relay: UDP ${IP}:${RELAY_PORT}"
echo "============================================"
curl -s "http://127.0.0.1:${API_PORT}/health" || true
echo ""
