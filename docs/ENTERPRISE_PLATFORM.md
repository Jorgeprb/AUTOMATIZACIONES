# Plataforma empresarial Autogal

Revisión lineal: `20260728_0020 -> 20260729_0022`.

## Capacidades

- CRM `ClinicCustomer` aislado por clínica, Caller ID E.164, CSV, campos, fusión y anonimización.
- Servicios con alias, trabajador preferido, recursos, capacidades, disponibilidad y reservas.
- Estadísticas tenant-safe y globales solo para superadministración.
- `CallAnalysis` asíncrono mediante `IntegrationOutbox`.
- Registro, verificación, recuperación, OAuth Google y onboarding multi-clínica.
- `BillingAccount`, catálogo persistido, Stripe, suscripciones, entitlements y provisión.
- SMTP/outbox, portal administrador, portal cliente, web pública y SIP gateway.

Toda ruta `/api/admin/clinics/{clinic_id}` aplica sesión, CSRF, membresía y rol. Los recursos anidados filtran simultáneamente por ID y clínica. Billing comprueba que la clínica pertenece a la cuenta comercial.

## Variables necesarias

```text
REGISTRATION_ENABLED
EMAIL_VERIFICATION_TTL_HOURS
PASSWORD_RESET_TTL_MINUTES
CLIENT_FRONTEND_BASE_URL
ADMIN_FRONTEND_BASE_URL
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM_EMAIL
SMTP_FROM_NAME
SMTP_USE_TLS
STRIPE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PHONE_PRICE_ID
STRIPE_MONTHLY_SERVICE_PRICE_ID
STRIPE_SUCCESS_URL
STRIPE_CANCEL_URL
STRIPE_CUSTOMER_PORTAL_RETURN_URL
CALL_ANALYSIS_ENABLED
CALL_ANALYSIS_MODEL
DEMO_PHONE_NUMBER
```

Conservar también las variables existentes de Google OAuth, OpenAI, Azure TTS, SIP, PostgreSQL y claves internas. No almacenar tarjetas ni IBAN.

## Stripe

Los importes salen de `BillingPrice.unit_amount_minor`; React solo envía IDs y cantidades. Configurar los Price IDs en el servidor.

Webhook:

```text
https://voice.autogal.es/api/webhooks/stripe
```

Eventos:

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

El body se verifica en bruto con `Stripe-Signature`. `WebhookReceipt` evita reprocesar eventos completados. Entitlements y provisión se activan solo tras pago confirmado. Customer Portal permite facturas, cambio de pago, cancelación al final del periodo y reactivación.

## Correo y OAuth

SMTP usa TLS y outbox con reintentos. Los tokens de verificación y recuperación son aleatorios, hasheados en base, caducan y solo se consumen una vez. Los logs no deben incluir enlaces completos.

Google debe declarar callbacks separados para portal cliente y administración. Mantener HTTPS y hosts exactos de `CLIENT_FRONTEND_BASE_URL`, `ADMIN_FRONTEND_BASE_URL` y redirects configurados.

## Provisión

1. Webhook de pago confirmado.
2. `PhoneProvisioningOrder=paid_pending_provisioning`.
3. Superadministración asigna número, proveedor, destino SIP y webhook.
4. Al activar se crea o actualiza `PhoneNumber`, se activa el entitlement y se encola el correo.
5. Verificar llamada entrante, contexto tenant y healthcheck SIP.

## Despliegue

```bash
cd /opt/AUTOMATIZACIONES
docker compose -f docker-compose.prod.yml --env-file .env.production config >/tmp/autogal-compose-rendered.yml
docker compose -f docker-compose.prod.yml --env-file .env.production build migrate api sip-gateway frontend client-frontend public-frontend
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate api sip-gateway frontend client-frontend public-frontend caddy
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --entrypoint alembic migrate current
```

Comprobar registro, OAuth, onboarding, acceso cruzado 403, CRM, disponibilidad, reserva, Checkout test, webhook duplicado, provisión, contexto conocido/desconocido y análisis encolado.

## Rollback

Con datos Enterprise: restaurar backup PostgreSQL previo y las imágenes anteriores. Sin datos nuevos:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --entrypoint alembic migrate downgrade 20260728_0020
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate api sip-gateway frontend client-frontend public-frontend caddy
```

No usar `alembic stamp`, no ejecutar `down -v` y no eliminar volúmenes.
