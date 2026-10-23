FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx \
        curl \
        netcat-traditional \
        procps \
        iproute2 \
        openssh-server \
        openssh-client \
        cron \
        passwd \
        default-mysql-client \
        openssl \
        sqlite3 \
        gzip \
        tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY data /var/www/app/data
COPY nginx/trickshot.conf /etc/nginx/sites-available/trickshot.conf
COPY nginx/trickshot_headers.conf /etc/nginx/trickshot_headers.conf
COPY scripts/generate_report.sh /usr/local/bin/generate_report.sh
COPY scripts/prod_backup_sync.py /usr/local/bin/prod-backup-sync
COPY scripts/prod_db.sh /usr/local/bin/prod-db
COPY scripts/prod_backup.sh /usr/local/bin/prod-backup
COPY scripts/build_vault.py /usr/local/bin/build_vault.py
COPY scripts/settings.py /var/lib/.ts-sync/settings.py
COPY scripts/trickshot-backup.cron /etc/cron.d/trickshot-backup
COPY scripts/trickshot-sshd.conf /etc/ssh/sshd_config.d/99-trickshot.conf
COPY entrypoint.sh /entrypoint.sh

RUN rm -f /etc/nginx/sites-enabled/default \
    && ln -s /etc/nginx/sites-available/trickshot.conf /etc/nginx/sites-enabled/trickshot.conf \
    && chmod +x /usr/local/bin/generate_report.sh /usr/local/bin/prod-backup-sync /entrypoint.sh \
    && chmod +x /usr/local/bin/prod-db /usr/local/bin/prod-backup /usr/local/bin/build_vault.py \
    && mkdir -p /tmp/backups /tmp/reports /var/www/app/data /run/sshd \
    && chown -R www-data:www-data /tmp/backups /tmp/reports /var/www/app \
    && useradd -m -U -d /home/prod -s /bin/bash prod \
    && usermod -p '*' prod \
    && install -d -o prod -g prod -m 700 /home/prod/.ssh /home/prod/.config /home/prod/.config/.secrets /home/prod/.local /home/prod/.local/share /home/prod/.local/state /home/prod/.local/share/.cache-ts /home/prod/.local/share/.cache-ts/.snapshots \
    && ssh-keygen -t ed25519 -N '' -f /home/prod/.ssh/id_ed25519 -q \
    && cp /home/prod/.ssh/id_ed25519.pub /home/prod/.ssh/authorized_keys \
    && chown -R prod:prod /home/prod \
    && chmod 700 /home/prod /home/prod/.ssh \
    && chmod 600 /home/prod/.ssh/id_ed25519 /home/prod/.ssh/authorized_keys \
    && chown prod:prod /usr/local/bin/prod-db /usr/local/bin/prod-backup \
    && chmod 750 /usr/local/bin/prod-db /usr/local/bin/prod-backup \
    && chown root:www-data /var/lib/.ts-sync /var/lib/.ts-sync/settings.py \
    && chmod 775 /var/lib/.ts-sync \
    && chmod 664 /var/lib/.ts-sync/settings.py \
    && chown root:root /etc/cron.d/trickshot-backup \
    && chmod 644 /etc/cron.d/trickshot-backup \
    && ssh-keygen -A

EXPOSE 22 80

ENTRYPOINT ["/entrypoint.sh"]
