# Despliegue VPS completo con SIP/RTP

Esta guía levanta toda la plataforma en un VPS real:

```text
Internet
  ├─ HTTPS 80/443 -> Caddy -> frontend nginx / FastAPI
  └─ SIP/RTP UDP -> sip-gateway -> FastAPI interno -> OpenAI + TTS provider
```

Servicios Docker:

- `api`: FastAPI, Alembic, herramientas, Google Calendar, OpenAI webhook.
- `frontend`: React/Vite compilado servido por nginx.
- `sip-gateway`: SIP/RTP propio para VPS Media Bridge.
- `caddy`: TLS automático y reverse proxy.
- `postgres`: opcional con perfil `local-db`.
- `redis`: opcional con perfil `redis`, reservado para locks/heartbeat futuros.

## Requisitos

VPS Ubuntu 22.04/24.04 o Debian 12 con:

- 1-2 vCPU.
- 1-2 GB RAM mínimo.
- IP pública fija.
- Puertos UDP abiertos por el proveedor cloud.
- Dominio apuntando al VPS.

Recomendación pequeña:

- si usas Supabase/Postgres externo, 1 GB RAM puede bastar;
- si usas Postgres local, mejor 2 GB RAM.

## DNS

Crea dos registros `A` hacia la IP pública del VPS:

```text
voice.example.com       A  IP_PUBLICA_VPS
admin.voice.example.com A  IP_PUBLICA_VPS
```

Usa esos valores en:

```env
APP_DOMAIN=voice.example.com
APP_ADMIN_DOMAIN=admin.voice.example.com
PUBLIC_BASE_URL=https://voice.example.com
FRONTEND_BASE_URL=https://admin.voice.example.com
GOOGLE_REDIRECT_URI=https://voice.example.com/auth/google/callback
```

## Firewall UFW

`ngrok http` y `cloudflared tunnel` no sirven para SIP/RTP. Solo exponen HTTP;
la llamada real necesita UDP SIP y UDP RTP directos al VPS.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 6060/udp
sudo ufw allow 10000:20000/udp
sudo ufw enable
sudo ufw status verbose
```

Si cambias `SIP_PORT`, `RTP_PORT_MIN` o `RTP_PORT_MAX`, cambia también UFW y el
firewall del proveedor cloud.

## Instalar Docker

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Cierra sesión y vuelve a entrar para usar Docker sin `sudo`.

## Variables

En la raíz del repo:

```bash
cp .env.production.example .env.production
nano .env.production
```

Mínimo obligatorio:

```env
APP_DOMAIN=voice.example.com
APP_ADMIN_DOMAIN=admin.voice.example.com
CADDY_EMAIL=admin@example.com
APP_ENVIRONMENT=production
INTERNAL_API_KEY=...
ADMIN_API_KEY=...
DATABASE_URL=...
OPENAI_API_KEY=...
OPENAI_WEBHOOK_SECRET=...
OPENAI_PROJECT_ID=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://voice.example.com/auth/google/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=...
SIP_PUBLIC_DOMAIN=sip.autogal.es
SIP_PUBLIC_IP=51.210.180.115
RTP_ADVERTISE_IP=51.210.180.115
SIP_PORT=6060
RTP_PORT_MIN=10000
RTP_PORT_MAX=20000
OPENAI_HOSTED_SIP_STRATEGY=blocked
# Si VoIP Studio llama a un alias como sip:bot@sip.autogal.es:6060,
# configura aquí el DID real de la clínica para que el gateway resuelva tenant.
FALLBACK_CALLED_NUMBER=+34XXXXXXXXX
```

Para Supabase, usa `DATABASE_URL` externo. Para Postgres local, deja:

```env
DATABASE_URL=postgresql+psycopg://clinic:PASSWORD@postgres:5432/clinic
POSTGRES_DB=clinic
POSTGRES_USER=clinic
POSTGRES_PASSWORD=PASSWORD
```

## Desplegar

Con DB externa:

```bash
grep -q '^COMPOSE_PROFILES=' .env.production && sed -i 's/^COMPOSE_PROFILES=.*/COMPOSE_PROFILES=/' .env.production
bash scripts/deploy_vps.sh
```

Con Postgres local, el ejemplo ya trae `COMPOSE_PROFILES=local-db`:

```bash
bash scripts/deploy_vps.sh
```

Con Redis opcional:

```bash
docker compose -f docker-compose.prod.yml \
  --env-file .env.production \
  --profile redis \
  up -d --build
```

## Healthchecks

HTTPS:

```bash
curl -fsS https://voice.example.com/health/ready
curl -fsS https://admin.voice.example.com
```

SIP:

```bash
python3 scripts/healthcheck_sip.py
```

Métricas internas del gateway:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production \
  exec sip-gateway python - <<'PY'
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:8088/metrics").read().decode())
PY
```

Devuelve, entre otros:

- `active_calls`
- `rtp_active`
- `sessions_orphaned`
- `tts_latency_ms_latest`
- `first_audio_latency_ms_latest`
- `invite_failures`
- `provider_errors`

## Google OAuth

En Google Cloud:

- JavaScript origin:

```text
https://admin.voice.example.com
```

- Redirect URI:

```text
https://voice.example.com/auth/google/callback
```

## OpenAI webhook

Configura en OpenAI:

```text
https://voice.example.com/webhooks/openai/realtime
```

El test event de OpenAI debe devolver `200`.

## VoIP Studio

Para VPS Media Bridge, no uses el endpoint SIP de OpenAI. Apunta VoIP Studio al
VPS. Para Sabela/Azure:

```text
sip:bot@sip.autogal.es:6060
```

El alias `bot` solo identifica la ruta SIP del gateway. La clínica se resuelve por
DID real. Si VoIP Studio no entrega el DID en `To`/Request-URI, define
`FALLBACK_CALLED_NUMBER` con el número público de esa clínica. El backend solo usa
fallback sin DID cuando hay una única clínica activa con configuración activa, para
evitar cruzar datos entre tenants.

Prueba interna del contrato gateway -> backend desde la red Docker:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec sip-gateway sh -lc '
python - <<"PY"
import json, os, urllib.request
url = os.environ.get("BACKEND_INTERNAL_URL", "http://api:10000") + "/api/internal/voice/context"
payload = {
    "caller": "+34600111222",
    "caller_phone": "+34600111222",
    "callee": "bot",
    "called_number": os.environ.get("FALLBACK_CALLED_NUMBER", ""),
    "sip_to": "<sip:bot@sip.autogal.es:6060>",
    "sip_from": "<sip:+34600111222@voipstudio.example>",
    "openai_call_id": "diag-context",
    "provider_call_id": "diag-context",
}
request = urllib.request.Request(
    url,
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "X-Internal-API-Key": os.environ["INTERNAL_API_KEY"],
    },
    method="POST",
)
print(urllib.request.urlopen(request, timeout=10).read().decode()[:2000])
PY'
```

Mantén el número en VoIP Studio. No hace falta portarlo.

OpenAI Hosted SIP directo sigue funcionando cuando VoIP Studio llama al SIP de
OpenAI. Pero si VoIP Studio llama siempre al gateway `sip.autogal.es:6060`, no
uses 302 por defecto: VoIP Studio puede colgar al pasar de UDP a TLS. Por eso
`OPENAI_HOSTED_SIP_STRATEGY=blocked` devuelve error SIP claro `488` en lugar de
dejar una llamada rota. El B2BUA TLS completo queda pendiente. Si quieres probar
el comportamiento antiguo, cambia a `OPENAI_HOSTED_SIP_STRATEGY=redirect`.

Si tienes IPs conocidas de VoIP Studio, limita:

```env
SIP_ALLOWED_IPS=IP_1,IP_2,CIDR_3
```

Si no sabes las IPs al principio, déjalo vacío, prueba, mira logs y luego
restringe.

## Logs

Todos los servicios usan `json-file` con rotación.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f api
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f sip-gateway
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f caddy
```

Buscar una llamada:

```bash
bash scripts/logs_call.sh CALL_ID_O_TELEFONO
```

## Backup DB

```bash
bash scripts/backup_db.sh
```

Con Postgres local hace `pg_dump` dentro del contenedor. Con DB externa usa un
contenedor `postgres:16-alpine` contra `DATABASE_URL`.

Guarda los `.sql.gz` fuera del VPS o en almacenamiento cifrado.

## Rotación de secretos

1. Cambia el secreto en `.env.production`.
2. Si es `ADMIN_API_KEY` o `INTERNAL_API_KEY`, reinicia `api`, `caddy` y
   `sip-gateway`.
3. Si es `OPENAI_API_KEY` o provider TTS, reinicia `api` y `sip-gateway`.
4. Si es `GOOGLE_TOKEN_ENCRYPTION_KEY`, no lo cambies salvo migración controlada:
   cifra tokens OAuth guardados. Rotarlo sin migración rompe Google Calendar.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate api caddy sip-gateway
```

## Seguridad

- No pongas ninguna clave administrativa en variables `VITE_*`; el panel usa sesión HttpOnly.
- Caddy no inyecta claves administrativas. El navegador usa sesiones HttpOnly,
  CSRF y permisos persistentes por clínica.
- Puedes añadir Cloudflare Access o VPN como segunda barrera, no como sustituto
  de la autenticación del backend.
- Usa `SIP_ALLOWED_IPS` cuando tengas IPs de VoIP Studio.
- Configura límites por clínica desde el panel y límites globales:
  `MAX_CONCURRENT_CALLS`, `MAX_CALL_SECONDS`, `INVITE_RATE_LIMIT_PER_MINUTE`.
- No abras Postgres al público.

## Troubleshooting

### No funciona HTTPS

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs caddy
dig +short voice.example.com
dig +short admin.voice.example.com
```

Comprueba que DNS apunta al VPS y que 80/443 están abiertos.

### No llega INVITE SIP

```bash
sudo tcpdump -ni any udp port 6060
```

Si no ves paquetes, el problema está en VoIP Studio, firewall cloud o UFW.

### Llega SIP pero no hay audio

```bash
sudo tcpdump -ni any udp portrange 10000-10100
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f sip-gateway
```

Comprueba:

- `RTP_ADVERTISE_IP` es la IP pública;
- UFW y firewall cloud abren todo el rango RTP;
- VoIP Studio negocia PCMU o PCMA.

### Ver SIP más cómodo con sngrep

```bash
sudo apt-get install -y sngrep
sudo sngrep -d any port 6060
```

### OpenAI/TTS falla

Busca `provider_errors`, `tts_chunk_failed` o errores 401/403:

```bash
curl -fsS http://127.0.0.1:8088/metrics
docker compose -f docker-compose.prod.yml --env-file .env.production logs --since 30m api sip-gateway
```

### Google Calendar no reserva

```bash
curl -fsS https://voice.example.com/health/ready
docker compose -f docker-compose.prod.yml --env-file .env.production logs --since 30m api
```

Revisa `GOOGLE_REDIRECT_URI`, cuenta conectada y calendarios enlazados a
trabajadores.
