# Deploy to Alibaba Cloud (CMS server, `focms.megaannum.ai:8001`)

Runs **API + MongoDB** in Docker alongside the existing CMS on the same server.

## Architecture

```
https://focms.megaannum.ai      (443) → CMS        → 127.0.0.1:8000
https://focms.megaannum.ai:8001 (8001) → EBC API  → 127.0.0.1:8002 (Docker)
```

Mobile app production URL: `https://focms.megaannum.ai:8001`

## Files in `deploy/`

| File | Purpose |
|------|---------|
| `docker-compose.prod.yml` | API + MongoDB containers |
| `start.sh` | Build and start containers |
| `nginx/focms-ebc-8001.conf` | nginx SSL on port 8001 |
| `.env.production.example` | Template for server `.env` |
| `setup-server.sh` | One-time Docker/nginx install (skip if CMS server already set up) |

**Not in git (upload separately):** `.env`, `firebase-service-account.json` in repo root.

---

## 1. Clone on server

```bash
cd /opt
git clone https://github.com/jfung2019/e-business-card-api.git
cd e-business-card-api
```

## 2. Upload secrets from your PC

```powershell
scp C:\Projects\E-business-card\e-business-card-api\.env root@8.217.183.31:/opt/e-business-card-api/
scp C:\Projects\E-business-card\e-business-card-api\firebase-service-account.json root@8.217.183.31:/opt/e-business-card-api/
```

Or on server: `cp deploy/.env.production.example .env` then `nano .env`.

## 3. Install Docker (if needed)

```bash
docker --version || curl -fsSL https://get.docker.com | sh
```

Or: `sudo bash deploy/setup-server.sh` for full one-time setup.

## 4. Start API + MongoDB

```bash
cd /opt/e-business-card-api
chmod +x deploy/*.sh
bash deploy/start.sh
```

Verify:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8002/docs
# → 200
docker ps   # ebc-api, ebc-mongodb
```

## 5. nginx (port 8001)

SSL for `focms.megaannum.ai` should already exist from CMS setup.

```bash
sudo cp deploy/nginx/focms-ebc-8001.conf /etc/nginx/sites-available/ebc-api
sudo ln -sf /etc/nginx/sites-available/ebc-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

If cert paths differ, check: `sudo ls /etc/letsencrypt/live/`

## 6. Alibaba firewall

Open TCP **8001** (80 and 443 should already be open for CMS).

## 7. Test

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://focms.megaannum.ai:8001/docs
```

On phone (any network): `https://focms.megaannum.ai:8001/docs`

---

## Updates

```bash
cd /opt/e-business-card-api
git pull
bash deploy/start.sh
```

## Useful commands

| Task | Command |
|------|---------|
| API logs | `docker logs -f ebc-api` |
| Restart | `docker compose -f deploy/docker-compose.prod.yml restart` |
| Stop | `docker compose -f deploy/docker-compose.prod.yml down` |
| Renew SSL | `sudo certbot renew --dry-run` |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `:8001` timeout | Open port 8001 in Alibaba firewall |
| `502 Bad Gateway` | `bash deploy/start.sh`, check `docker logs ebc-api` |
| nginx cert error | Match paths in `/etc/letsencrypt/live/focms.megaannum.ai/` |
| Missing secrets | Ensure `.env` and `firebase-service-account.json` in repo root |
| **413** on card scan (front + back) | nginx default upload limit is 1 MB. After `git pull`, copy `deploy/nginx/focms-ebc-8001.conf` and `sudo nginx -t && sudo systemctl reload nginx` (`client_max_body_size 25m`) |
| App shows **Parsing service is busy** | Upload reached the API but OpenRouter parsing failed. Run `git pull && bash deploy/start.sh` (rebuilds the API container). Check `docker logs --tail 100 ebc-api` for `OpenRouter error` lines. |
