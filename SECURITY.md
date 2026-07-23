# Seguridad

El panel usa sesiones opacas almacenadas en PostgreSQL. La cookie de sesión es
`HttpOnly`, `Secure` en producción y las escrituras requieren CSRF de doble envío.
`ADMIN_API_KEY` queda reservado para automatizaciones servidor-servidor y nunca se
incluye en el bundle Vite ni se inyecta desde Caddy.

## Producción

- Ejecutar las migraciones antes de iniciar la API.
- Limitar UDP/6060 y el rango RTP a los rangos del proveedor en firewall y en
  `SIP_ALLOWED_IPS`/`RTP_ALLOWED_IPS`.
- Mantener API y PostgreSQL en redes Docker internas.
- Usar el script de release para no empaquetar `.env`, backups ni caches.
- Revisar `/metrics`, logs de auditoría y entregas duplicadas de webhook.
- Notificar vulnerabilidades de forma privada al responsable del despliegue.
