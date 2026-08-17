#!/bin/bash
# Install cloudflared + systemd service on Aeza VPS (run once as root)
set -euo pipefail

echo "==> cloudflared binary"
ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) CF_ARCH=amd64 ;;
  aarch64|arm64) CF_ARCH=arm64 ;;
  *) echo "Unsupported arch: $ARCH"; exit 1 ;;
esac

mkdir -p /tmp/cf-install
cd /tmp/cf-install

URLS=(
  "https://ghfast.top/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}"
  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}"
  "https://mirror.ghproxy.com/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}"
)

ok=0
for u in "${URLS[@]}"; do
  echo "try $u"
  if curl -fL --max-time 120 -o cloudflared "$u"; then
    ok=1
    break
  fi
done
if [ "$ok" != "1" ]; then
  echo "FAILED to download cloudflared"
  exit 1
fi

chmod +x cloudflared
mv -f cloudflared /usr/local/bin/cloudflared
cloudflared --version || true

echo "==> systemd unit"
cat >/etc/systemd/system/cloudflared-snake.service << 'EOF'
[Unit]
Description=Cloudflare Tunnel — Multiplayer Snake API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000
Restart=always
RestartSec=5
User=root
StandardOutput=append:/var/log/cloudflared-snake.log
StandardError=append:/var/log/cloudflared-snake.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cloudflared-snake
sleep 8

echo "==> waiting for trycloudflare URL in log..."
URL=""
for i in 1 2 3 4 5 6 7 8 9 10; do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /var/log/cloudflared-snake.log 2>/dev/null | tail -1 || true)
  if [ -n "$URL" ]; then break; fi
  sleep 3
done

echo ""
echo "============================================"
if [ -n "$URL" ]; then
  echo " TUNNEL URL: $URL"
  echo " Health:     $URL/health"
  curl -sS --max-time 10 "$URL/health" || true
  echo ""
  echo " Put this URL into GitHub file api_url.txt (one line)."
  echo " App reads it automatically — no APK rebuild."
else
  echo " Tunnel started but URL not found yet."
  echo " Run: tail -f /var/log/cloudflared-snake.log"
fi
echo "============================================"
echo " systemctl status cloudflared-snake"
systemctl --no-pager status cloudflared-snake || true
