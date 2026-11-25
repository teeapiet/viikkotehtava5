#!/usr/bin/env bash
set -euo pipefail

REVISION="${1:-}"
if [[ ! "$REVISION" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Anna julkaisun 40-merkkinen Git-commit-tunniste."
    exit 1
fi

cd /opt/chatapp/app

if ! sudo grep -REq \
    '^[[:space:]]*include[[:space:]]+(/etc/nginx/)?snippets/chatapp\.conf[[:space:]]*;' \
    /etc/nginx/sites-enabled/; then
    echo "Nginxin sivustosta puuttuu include snippets/chatapp.conf;"
    exit 1
fi

if [ ! -d /opt/chatapp/venv ]; then
    python3 -m venv /opt/chatapp/venv
fi
/opt/chatapp/venv/bin/python -m pip install -r requirements.txt

sudo mysql chatapp < deploy/sql/schema.sql
printf '%s\n' "$REVISION" > REVISION

BACKUP=$(mktemp -d)
SNIPPET=/etc/nginx/snippets/chatapp.conf
RATE=/etc/nginx/conf.d/chatapp-rate.conf

sudo cp -p "$SNIPPET" "$BACKUP/snippet"
HAD_RATE=0
if sudo test -f "$RATE"; then
    sudo cp -p "$RATE" "$BACKUP/rate"
    HAD_RATE=1
fi

sudo install -m 644 deploy/nginx/chatapp.conf "$SNIPPET"
sudo install -m 644 deploy/nginx/chatapp-rate.conf "$RATE"

if ! sudo nginx -t; then
    sudo cp -p "$BACKUP/snippet" "$SNIPPET"
    if [ "$HAD_RATE" = "1" ]; then
        sudo cp -p "$BACKUP/rate" "$RATE"
    else
        sudo rm -f "$RATE"
    fi
    echo "Nginx-asetukset eivät kelvanneet. Edelliset asetukset palautettiin."
    exit 1
fi

sudo install -m 644 deploy/systemd/chatapp.service \
    /etc/systemd/system/chatapp.service
sudo systemctl daemon-reload
sudo systemctl enable chatapp
sudo systemctl restart chatapp
sudo systemctl reload nginx

for _ in $(seq 1 20); do
    if sudo curl -fsS --unix-socket /run/chatapp/gunicorn.sock \
        http://localhost/health | grep -Fxq "$REVISION"; then
        echo "Julkaisu onnistui: $REVISION"
        exit 0
    fi
    sleep 2
done

sudo journalctl -u chatapp -n 50 --no-pager
echo "Chat-palvelun terveystarkistus epäonnistui."
exit 1
