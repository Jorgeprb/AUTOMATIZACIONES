# Estado de mejoras

Implementado en código: autenticación persistente, CSRF, RBAC por clínica,
auditoría, bloqueo de fuerza bruta, eliminación de credenciales del bundle,
Caddy seguro, SSRF, redacción de PII, Docker no privilegiado, redes internas,
migración independiente, idempotencia de reservas/webhooks, exclusión de
solapamientos, outbox, retención programada, RTP fijado por origen/SSRC,
parsing RTP con padding/extensiones, wrap de secuencia, ciclo SIP idempotente,
timeout de ACK, colas acotadas, clientes HTTP reutilizados, OpenMetrics, error
boundary, paginación completa de clínicas, Realtime GA en la previsualización,
CI, Dependabot y empaquetado limpio.

Requieren infraestructura externa y no pueden activarse solo modificando el
repositorio: firewall del proveedor, un B2BUA industrial (Kamailio/OpenSIPS +
Asterisk/FreeSWITCH) si Hosted SIP necesita proxy TLS, almacenamiento off-site,
colector OpenTelemetry, SMS/WhatsApp, AEC de operador y un HIS/CRM concreto.
El repositorio deja documentados los límites para que estas integraciones no se
simulen ni se presenten como activas.
