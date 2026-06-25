# Clinic Voice Admin

Panel React para administrar la plataforma multi-clínica del asistente
telefónico.

## Stack

- React + TypeScript estricto + Vite
- Tailwind CSS y componentes locales estilo shadcn/ui
- TanStack Query
- React Hook Form + Zod
- React Router, lucide-react y Sonner
- Vitest + Testing Library

## Configuración

```powershell
Copy-Item .env.example .env
```

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_ADMIN_API_KEY=la-misma-clave-que-ADMIN_API_KEY
VITE_ENABLE_DEV_FALLBACKS=false
```

El backend debe permitir el origen:

```dotenv
CORS_ORIGINS=http://localhost:5173
```

La API key se inyecta en el build de Vite. Esto solo es aceptable para el MVP
local. Antes de publicar el panel se necesita login y una capa servidor que no
exponga `ADMIN_API_KEY` al navegador.

## Arranque

```powershell
cd ..\clinic-voice-agent
docker compose up -d
docker compose run --rm app alembic upgrade head
docker compose run --rm app python -m scripts.seed_demo

cd ..\frontend
npm install
npm run dev
```

Abre <http://localhost:5173>.

## Flujo de configuración

1. Crea o selecciona una clínica.
2. Edita sus datos, horario general, mensaje de emergencia y retención.
3. Añade el número telefónico y su destino OpenAI SIP.
4. En Calendario, conecta la cuenta Google de la clínica mediante OAuth.
5. Crea trabajadores y define sus horarios semanales.
6. Crea un calendario secundario por trabajador o enlaza uno existente.
7. Elige el color del trabajador y prueba FreeBusy.
8. Crea los servicios, duración y precios.
9. Configura el asistente, sus prompts y la base de conocimiento.
10. Usa la consola de prueba antes de conectar llamadas reales.

## Funcionalidad operativa

- edición completa de clínica;
- CRUD de números y avisos de SIP sin configurar;
- CRUD de trabajadores;
- editor semanal con días cerrados y varios tramos;
- CRUD de servicios, precios, duración, buffers y trabajadores permitidos;
- filtros de servicios activos/inactivos y avisos de configuración incompleta;
- CRUD de conocimiento con búsqueda, categorías, prioridad y activación rápida;
- vista previa del contexto efectivo y del prompt final;
- CRUD de configuraciones del asistente con activación exclusiva;
- flujos conversacionales JSON con plantillas, validación, asociación al
  asistente y preview del prompt;
- selector local de modelos, voces e idiomas, incluido `es-ES` y `gl-ES`;
- plantillas para dental, peluquería, fisioterapia, psicología, medicina
  estética y clínica general;
- preferencias de transcripción, grabación y retención por configuración;
- estado OAuth, conexión Google y listado de calendarios;
- creación y enlace de calendarios por trabajador;
- selección de color y diagnóstico FreeBusy;
- badges de trabajador activo, inactivo y calendario conectado;
- dashboard, servicios, asistente, conocimiento, llamadas y citas.
- dashboard operativo con métricas de 24 horas y checklist de producción.

## Scripts

```text
npm run dev        servidor Vite
npm run typecheck  TypeScript estricto
npm run test       pruebas Vitest
npm run build      typecheck y build de producción
npm run preview    previsualiza dist/
```

La consola `/clinics/:clinicId/test` usa por defecto el simulador local y un
calendario fake. Puede cambiarse al motor OpenAI y activar Google Calendar real
de forma explícita. El modelo textual se configura con `TEST_CONSOLE_MODEL` en
el backend.

Desde la raíz del repositorio también puede arrancarse todo con:

```text
docker compose up --build
```

Este comando inicia PostgreSQL, aplica migraciones, arranca FastAPI y publica
el panel en `http://localhost:5173`.

No se usan datos falsos por defecto. Los fallos de API aparecen como estados
de error y toasts.
