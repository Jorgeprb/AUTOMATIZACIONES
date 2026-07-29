# Plataforma empresarial Autogal

Esta entrega amplía Autogal sin sustituir los modelos ni migraciones existentes. La revisión nueva es lineal:

```text
20260728_0020 -> 20260729_0022
```

## Capacidades

- CRM `ClinicCustomer` aislado por clínica, con importación/exportación, campos personalizados, historial, fusión y anonimización.
- Reconocimiento del llamante por DID y número E.164 dentro de una sola clínica.
- Alias y expresiones de servicios, profesional preferido y recursos de capacidad limitada.
- Estadísticas por clínica y vistas globales para superadministración.
- Análisis asíncrono e idempotente de llamadas mediante `IntegrationOutbox`.
- Registro autónomo, verificación de correo, recuperación de contraseña y onboarding.
- `BillingAccount` con varios usuarios y varias clínicas.
- Catálogo persistido y administrable de productos y precios.
- Stripe Checkout, Customer Portal, webhooks verificados y provisión manual de números.
- Entitlements validados en FastAPI para llamadas de producción.
- Correo SMTP fiable mediante outbox.

## Variables nuevas de `.env.production`

Añade estas variables conservando todas las existentes:

```dotenv
REGISTRATION_ENABLED=true
EMAIL_VERIFICATION_TTL_HOURS=24
PASSWORD_RESET_TTL_MINUTES=30

SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Autogal
SMTP_USE_TLS=true

STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PHONE_PRICE_ID=
STRIPE_MONTHLY_SERVICE_PRICE_ID=
STRIPE_SUCCESS_URL=https://client.autogal.es/purchases?checkout=success
STRIPE_CANCEL_URL=https://client.autogal.es/purchases?checkout=cancelled
STRIPE_CUSTOMER_PORTAL_RETURN_URL=https://client.autogal.es/purchases

CALL_ANALYSIS_ENABLED=true
CALL_ANALYSIS_MODEL=gpt-5.6-luna
DEMO_PHONE_NUMBER=+34881170837
```

No guardes números de tarjeta, IBAN, contraseñas de VoIP Studio ni secretos de Stripe en la base o el repositorio.

## Stripe Dashboard

### Producto 1

- Nombre: `Número de teléfono Autogal`
- Tipo de precio: pago único
- Importe: `15.00 EUR`
- Copiar el Price ID a `STRIPE_PHONE_PRICE_ID`.

### Producto 2

- Nombre: `Servicio mensual Autogal`
- Tipo de precio: recurrente mensual
- Importe: `50.00 EUR / month`
- Copiar el Price ID a `STRIPE_MONTHLY_SERVICE_PRICE_ID`.

El catálogo local se sincroniza con esos Price IDs y también puede ampliarse desde el panel global **Negocio y provisión**. Los importes del Checkout se calculan desde `BillingPrice`; el navegador nunca decide el precio.

### Webhook

Registra:

```text
https://voice.autogal.es/api/webhooks/stripe
```

Eventos mínimos:

```text
checkout.session.completed
checkout.session.async_payment_succeeded
checkout.session.async_payment_failed
invoice.paid
invoice.payment_failed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
charge.refunded
```

Copia el signing secret a `STRIPE_WEBHOOK_SECRET`. La activación local ocurre solo al procesar webhooks verificados, nunca al regresar por `success_url`.

### Customer Portal

Activa en Stripe Customer Portal:

- actualización del método de pago;
- descarga de facturas;
- cancelación al final del periodo;
- reactivación antes de la fecha efectiva;
- retorno a `https://client.autogal.es/purchases`.

La compra permanente del número se conserva aunque termine la mensualidad. El entitlement `assistant_production` se desactiva conforme al estado proyectado por los webhooks.

## SMTP

Configura un buzón transaccional con TLS. Ejemplo conceptual:

```dotenv
SMTP_HOST=smtp.proveedor.example
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=secreto
SMTP_FROM_EMAIL=notificaciones@autogal.es
SMTP_FROM_NAME=Autogal
SMTP_USE_TLS=true
```

Se encolan correos para verificación, recuperación, compra, provisión, activación, pago fallido, cancelación y facturación. Las peticiones HTTP no esperan reintentos SMTP.

## Flujo de provisión

1. Stripe confirma el pago.
2. Se crea `PhoneProvisioningOrder` en `paid_pending_provisioning`.
3. El cliente ve el ETA inferior a 24 horas.
4. El superadministrador abre **Provisión de números**.
5. Introduce número, proveedor, ID externo, SIP target, webhook y notas.
6. Al marcar `active`, se crea/actualiza `PhoneNumber`, se activa el entitlement y se encola el email.

## Despliegue

```bash
cd /opt
cp -a AUTOMATIZACIONES "AUTOMATIZACIONES.backup.$(date +%Y%m%d_%H%M%S)"

cd /opt/AUTOMATIZACIONES

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  build --no-cache migrate api sip-gateway frontend client-frontend public-frontend

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  run --rm migrate

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  up -d --force-recreate \
  api sip-gateway frontend client-frontend public-frontend caddy
```

Comprobación:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps

docker compose -f docker-compose.prod.yml --env-file .env.production \
  logs --tail=200 migrate api sip-gateway frontend client-frontend public-frontend caddy

docker compose -f docker-compose.prod.yml --env-file .env.production \
  run --rm --entrypoint alembic migrate current

docker compose -f docker-compose.prod.yml --env-file .env.production \
  run --rm --entrypoint alembic migrate heads
```

Ambos comandos Alembic deben mostrar únicamente `20260729_0022 (head)`.

## Rollback

### Aplicación

Restaura el directorio respaldado y reconstruye las imágenes. Mantén la base en la revisión nueva si ya contiene CRM, compras o facturación; el código anterior no debe utilizar esas entidades, pero los datos permanecerán intactos.

### Base de datos

Solo si la migración acaba de aplicarse y no se han creado datos empresariales:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production \
  run --rm --entrypoint alembic migrate downgrade 20260728_0020
```

En producción con datos, el rollback recomendado es restaurar un backup PostgreSQL previo. No uses `alembic stamp`, `down -v` ni elimines volúmenes.

## Comandos de validación

```bash
python -m compileall -q clinic-voice-agent/app clinic-voice-agent/alembic sip-gateway/src

cd clinic-voice-agent
ruff check app tests
mypy app
pytest
alembic heads
DATABASE_URL='postgresql+psycopg://user:pass@localhost/db' alembic upgrade head --sql

cd ../sip-gateway
pytest

cd ../frontend
npm run typecheck
npm run test
npm run build

cd ../public-frontend
npm run typecheck
npm run build

cd ..
docker compose -f docker-compose.prod.yml --env-file .env.production config
caddy validate --config deploy/Caddyfile --adapter caddyfile
```

## DNS

No requiere cambios respecto a la topología existente:

- `www.autogal.es`
- `client.autogal.es`
- `admin.autogal.es`
- `voice.autogal.es`

