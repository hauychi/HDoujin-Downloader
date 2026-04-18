# Deployment

Two supported deployment paths: Docker Compose, or a native systemd service.

## Docker Compose

```bash
cp .env.example .env
cp portfolio.example.yaml portfolio.yaml
docker compose up -d --build
docker compose logs -f
```

State is persisted in the `rebalancer-state` named volume; `portfolio.yaml`
is mounted read-only. Logs are emitted as JSON lines to stdout so container
log drivers (Loki, CloudWatch, etc.) can parse them directly.

## systemd

```bash
sudo useradd --system --home /var/lib/crypto-rebalancer --shell /usr/sbin/nologin rebalancer

sudo mkdir -p /opt/crypto-rebalancer /etc/crypto-rebalancer /var/lib/crypto-rebalancer
sudo chown rebalancer:rebalancer /var/lib/crypto-rebalancer

# Install the app into /opt/crypto-rebalancer
sudo -u rebalancer python3 -m venv /opt/crypto-rebalancer/.venv
sudo -u rebalancer /opt/crypto-rebalancer/.venv/bin/pip install \
    "git+https://github.com/hauychi/hdoujin-downloader#subdirectory=crypto-rebalancer"

# Config (chmod 600; holds API keys)
sudo cp .env.example /etc/crypto-rebalancer/env
sudo cp portfolio.example.yaml /etc/crypto-rebalancer/portfolio.yaml
sudo chmod 600 /etc/crypto-rebalancer/env
sudo chown -R root:rebalancer /etc/crypto-rebalancer

# Install and start the unit
sudo cp deploy/crypto-rebalancer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-rebalancer.service
journalctl -u crypto-rebalancer -f
```

The unit runs with `--log-format json`, so `journalctl -o json` yields
structured records that can be forwarded to a log aggregator.
