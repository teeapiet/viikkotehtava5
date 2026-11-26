#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
    echo "Aja tämä ubuntu-käyttäjänä palvelimella A."
    exit 1
fi

sudo -n true
sudo systemctl is-active --quiet mariadb
sudo systemctl is-active --quiet ollama
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null

if [ "$(sudo mysql -Nse 'SELECT @@global.read_only')" != "0" ]; then
    echo "Tietokanta on read-only-tilassa. Älä muuta replikointia."
    exit 1
fi

if ! id chatapp >/dev/null 2>&1; then
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin chatapp
fi

sudo install -d -m 755 -o ubuntu -g ubuntu /opt/chatapp /opt/chatapp/app
sudo install -d -m 700 -o root -g root /etc/chatapp

if ! sudo test -f /etc/chatapp/chatapp.env; then
    EXISTING=$(sudo mysql -Nse "
        SELECT
          (SELECT COUNT(*) FROM information_schema.schemata
           WHERE schema_name='chatapp')
          +
          (SELECT COUNT(*) FROM mysql.user WHERE User='chatapp');
    ")
    if [ "$EXISTING" != "0" ]; then
        echo "chatapp-tietokanta tai käyttäjä on jo olemassa."
        echo "Pysähdytään, jotta olemassa olevia asetuksia ei korvata."
        exit 1
    fi

    DB_PASSWORD=$(openssl rand -hex 24)

    sudo mysql <<SQL
CREATE DATABASE chatapp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'chatapp'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
GRANT SELECT, INSERT, DELETE ON chatapp.* TO 'chatapp'@'127.0.0.1';
SQL

    sudo install -m 600 -o root -g root /dev/null /etc/chatapp/chatapp.env
    sudo tee /etc/chatapp/chatapp.env >/dev/null <<ENV
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=chatapp
DB_USER=chatapp
DB_PASSWORD=$DB_PASSWORD
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:0.5b
HISTORY_LIMIT=10
SYSTEM_PROMPT="You are a friendly Linux tutor. Always reply in English. Keep answers short."
ENV
    unset DB_PASSWORD
else
    echo "Asetustiedosto on jo olemassa. Salasanaa ei muuteta."
fi

sudo install -d -m 755 /etc/nginx/snippets
if ! sudo test -e /etc/nginx/snippets/chatapp.conf; then
    echo '# Viikon 5 chat: deploy päivittää tämän.' |
        sudo tee /etc/nginx/snippets/chatapp.conf >/dev/null
fi

echo "Alustus valmis."
