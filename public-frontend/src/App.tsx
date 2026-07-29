import { Fragment, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  PhoneIncoming,
  Calendar,
  Clock,
  MessageSquare,
  Repeat,
  UserRoundCheck,
  ClipboardList,
  BarChart3,
  Moon,
  Menu,
  X,
  Check,
  Plus,
  Minus,
} from "lucide-react";

/* ---------- design tokens as JS ---------- */
const BRAND = "oklch(0.52 0.13 245)";
const BRAND_DEEP = "oklch(0.36 0.11 250)";
const INK = "oklch(0.19 0.035 255)";
const INK_SOFT = "oklch(0.42 0.025 255)";
const HAIRLINE = "oklch(0.9 0.008 250)";

/* =====================================================================
   NAV
   ===================================================================== */
function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header
      className={`sticky top-0 z-50 transition-colors ${
        scrolled
          ? "border-b hairline bg-[color-mix(in_oklab,var(--paper)_82%,transparent)] backdrop-blur"
          : "border-b border-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-[1320px] items-center justify-between px-6 lg:px-10">
        <a href="#top" className="flex items-center gap-2">
          <Wordmark />
        </a>
        <nav className="hidden items-center gap-8 lg:flex">
          {[
            ["Producto", "#producto"],
            ["Cómo funciona", "#como-funciona"],
            ["Resultados", "#resultados"],
            ["Soluciones", "#soluciones"],
            ["Preguntas frecuentes", "#faq"],
          ].map(([l, h]) => (
            <a
              key={h}
              href={h}
              className="text-[14px] font-medium text-ink-soft transition-colors hover:text-ink"
              style={{ color: INK_SOFT }}
            >
              {l}
            </a>
          ))}
        </nav>
        <div className="hidden items-center gap-2 lg:flex">
          <a
            href="/auth/login/google/start?portal=client&return_to=/"
            className="rounded-lg px-3 py-2 text-[14px] font-medium transition-colors hover:bg-[var(--paper-warm)]"
            style={{ color: INK }}
          >
            Acceder
          </a>
          <a href="https://client.autogal.es/register" className="btn-primary">
            Registrarse
          </a>
        </div>
        <button
          className="lg:hidden"
          onClick={() => setOpen(!open)}
          aria-label="Menú"
        >
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>
      {open && (
        <div className="border-t hairline lg:hidden">
          <div className="mx-auto flex max-w-[1320px] flex-col gap-1 px-6 py-4">
            {[
              ["Producto", "#producto"],
              ["Cómo funciona", "#como-funciona"],
              ["Resultados", "#resultados"],
              ["Soluciones", "#soluciones"],
              ["Preguntas frecuentes", "#faq"],
              ["Acceder", "/auth/login/google/start?portal=client&return_to=/"],
            ].map(([l, h]) => (
              <a
                key={h}
                href={h}
                onClick={() => setOpen(false)}
                className="py-2 text-[15px] font-medium"
              >
                {l}
              </a>
            ))}
            <a href="https://client.autogal.es/register" className="btn-primary mt-2 w-full justify-center">
              Registrarse
            </a>
          </div>
        </div>
      )}
    </header>
  );
}

function Wordmark() {
  return (
    <div className="flex items-baseline gap-[2px]">
      <span
        className="text-[19px] font-bold tracking-[-0.04em]"
        style={{ color: INK }}
      >
        autogal
      </span>
      <span
        className="text-[19px] font-bold"
        style={{ color: BRAND }}
        aria-hidden
      >
        .
      </span>
    </div>
  );
}

/* =====================================================================
   HERO
   ===================================================================== */
function Hero() {
  return (
    <section id="top" className="relative overflow-hidden">
      {/* subtle flow motif */}
      <FlowBackdrop />
      <div className="mx-auto max-w-[1320px] px-6 pt-16 pb-10 lg:px-10 lg:pt-24 lg:pb-16">
        <div className="max-w-[900px]">
          <div className="mb-8 flex items-center gap-3">
            <span className="eyebrow">Operaciones telefónicas</span>
            <span
              className="h-px w-10"
              style={{ background: HAIRLINE }}
              aria-hidden
            />
            <span
              className="text-[12px] font-medium"
              style={{ color: INK_SOFT }}
            >
              Plataforma para negocios de servicio
            </span>
          </div>
          <h1
            className="text-display text-[44px] leading-[1.04] sm:text-[56px] lg:text-[72px]"
            style={{ color: INK }}
          >
            Tu negocio no debería perder
            <br />
            oportunidades porque <em className="italic font-normal" style={{ color: BRAND_DEEP }}>nadie pudo</em>
            <br />
            coger el teléfono.
          </h1>
          <p
            className="mt-8 max-w-[620px] text-[18px] leading-[1.55]"
            style={{ color: INK_SOFT }}
          >
            Autogal atiende llamadas, resuelve consultas y gestiona parte de la
            demanda de tu negocio cuando tu equipo no puede responder.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-4">
            <a href="https://client.autogal.es/register" className="btn-primary">
              Registrarse <ArrowRight size={16} />
            </a>
            <a
              href="#como-funciona"
              className="group inline-flex items-center gap-2 text-[15px] font-semibold"
              style={{ color: INK }}
            >
              Ver cómo funciona
              <span
                className="inline-block h-px w-6 transition-all group-hover:w-10"
                style={{ background: INK }}
              />
            </a>
          </div>
        </div>

        <div className="mt-16 lg:mt-20">
          <ProductPreview />
        </div>
      </div>
    </section>
  );
}

function FlowBackdrop() {
  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-x-0 top-0 -z-0 h-[520px] w-full opacity-[0.35]"
      viewBox="0 0 1440 520"
      fill="none"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id="fadeLine" x1="0" x2="1">
          <stop offset="0" stopColor={BRAND} stopOpacity="0" />
          <stop offset="0.4" stopColor={BRAND} stopOpacity="0.35" />
          <stop offset="1" stopColor={BRAND} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[80, 160, 240, 320, 400].map((y, i) => (
        <path
          key={y}
          d={`M0 ${y} C 360 ${y - 30 + i * 8}, 900 ${y + 40 - i * 6}, 1440 ${y + 10}`}
          stroke="url(#fadeLine)"
          strokeWidth="1"
        />
      ))}
      {[
        [220, 120],
        [560, 190],
        [860, 130],
        [1120, 220],
      ].map(([x, y]) => (
        <g key={`${x}-${y}`}>
          <circle cx={x} cy={y} r="3" fill={BRAND} />
          <circle
            cx={x}
            cy={y}
            r="10"
            fill="none"
            stroke={BRAND}
            strokeOpacity="0.25"
          />
        </g>
      ))}
    </svg>
  );
}

/* =====================================================================
   PRODUCT PREVIEW (dashboard)
   ===================================================================== */
function ProductPreview() {
  return (
    <div
      className="relative overflow-hidden rounded-2xl border bg-white shadow-[0_1px_0_rgba(15,20,45,0.04),0_20px_60px_-20px_rgba(15,20,45,0.18)]"
      style={{ borderColor: HAIRLINE }}
    >
      {/* Top product bar */}
      <div
        className="flex items-center justify-between border-b px-5 py-3"
        style={{ borderColor: HAIRLINE }}
      >
        <div className="flex items-center gap-4">
          <Wordmark />
          <span className="hidden h-4 w-px sm:block" style={{ background: HAIRLINE }} />
          <div className="hidden items-center gap-2 sm:flex">
            <div
              className="flex items-center gap-2 rounded-md border px-2.5 py-1 text-[12.5px] font-medium"
              style={{ borderColor: HAIRLINE }}
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: BRAND }}
              />
              Negocio Norte
              <ArrowRight size={12} style={{ transform: "rotate(90deg)" }} />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[12px]" style={{ color: INK_SOFT }}>
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: "oklch(0.62 0.11 155)" }}
          />
          Activo en tiempo real
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr]">
        {/* Sidebar */}
        <aside
          className="hidden border-r p-5 text-[13px] lg:block"
          style={{ borderColor: HAIRLINE }}
        >
          {[
            ["Resumen", true],
            ["Llamadas", false],
            ["Reservas y citas", false],
            ["Análisis", false],
            ["Fuera de horario", false],
            ["Ajustes", false],
          ].map(([l, active]) => (
            <div
              key={l as string}
              className={`mb-1 rounded-md px-2.5 py-1.5 ${
                active ? "font-semibold" : "font-medium"
              }`}
              style={{
                background: active ? "var(--brand-soft)" : "transparent",
                color: active ? BRAND_DEEP : INK_SOFT,
              }}
            >
              {l as string}
            </div>
          ))}
        </aside>

        {/* Main */}
        <div className="p-6 lg:p-8">
          <div className="mb-1 text-[13px] font-medium" style={{ color: INK_SOFT }}>
            Buenos días
          </div>
          <h2 className="text-[22px] font-bold tracking-tight" style={{ color: INK }}>
            Esto es lo que Autogal ha gestionado este mes.
          </h2>

          <MetricRow />

          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1.55fr_1fr]">
            <ChartPanel />
            <InsightPanel />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricRow() {
  const items = [
    { v: "327", label: "Llamadas gestionadas", d: "+22,4 %" },
    { v: "64", label: "Reservas y citas gestionadas", d: "+11,2 %" },
    { v: "82 %", label: "Resolución autónoma", d: "+4,1 %" },
    {
      v: "14",
      label: "Gestiones fuera de horario",
      d: "+27,3 %",
      icon: <Moon size={13} />,
    },
  ];
  return (
    <div className="mt-7 grid grid-cols-2 lg:grid-cols-4">
      {items.map((m, i) => (
        <div
          key={m.label}
          className={`px-0 py-1 lg:px-6 ${i > 0 ? "lg:border-l" : ""} ${
            i === 2 ? "border-t lg:border-t-0" : ""
          } ${i === 3 ? "border-t lg:border-t-0" : ""}`}
          style={{ borderColor: HAIRLINE }}
        >
          <div className="flex items-baseline gap-2 pt-3 lg:pt-0">
            <div
              className="numeric text-[36px] font-bold leading-none tracking-[-0.03em]"
              style={{ color: INK }}
            >
              {m.v}
            </div>
            {m.icon && (
              <span style={{ color: INK_SOFT }} aria-hidden>
                {m.icon}
              </span>
            )}
          </div>
          <div
            className="mt-2 text-[13px] font-medium"
            style={{ color: INK_SOFT }}
          >
            {m.label}
          </div>
          <div
            className="mt-1 numeric text-[12px] font-semibold"
            style={{ color: BRAND_DEEP }}
          >
            {m.d}
          </div>
        </div>
      ))}
    </div>
  );
}

function ChartPanel() {
  return (
    <div
      className="rounded-xl border p-5"
      style={{ borderColor: HAIRLINE }}
    >
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[13px] font-semibold" style={{ color: INK }}>
            Llamadas gestionadas
          </div>
          <div className="text-[12px]" style={{ color: INK_SOFT }}>
            Últimos 6 meses
          </div>
        </div>
        <div className="flex gap-1">
          {["6M", "3M", "1M"].map((k, i) => (
            <span
              key={k}
              className="rounded-md px-2 py-1 text-[11px] font-semibold"
              style={{
                background: i === 0 ? "var(--brand-soft)" : "transparent",
                color: i === 0 ? BRAND_DEEP : INK_SOFT,
              }}
            >
              {k}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-4 h-[210px]">
        <CallsLineChart />
      </div>
    </div>
  );
}

function CallsLineChart({ dark = false }: { dark?: boolean }) {
  const values = [168, 192, 210, 238, 276, 327];
  const labels = ["Feb", "Mar", "Abr", "May", "Jun", "Jul"];
  const width = 720;
  const height = 240;
  const padding = 24;
  const max = Math.max(...values);
  const points = values.map((value, index) => ({
    x: padding + (index * (width - padding * 2)) / (values.length - 1),
    y: height - padding - (value / max) * (height - padding * 2),
    value,
    label: labels[index],
  }));
  return (
    <div className="h-full w-full overflow-hidden" role="img" aria-label="Llamadas gestionadas en los últimos seis meses">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full" aria-hidden="true">
        {[0.25, 0.5, 0.75, 1].map((ratio) => <line key={ratio} x1={padding} y1={height-padding-ratio*(height-padding*2)} x2={width-padding} y2={height-padding-ratio*(height-padding*2)} stroke={dark ? "rgba(255,255,255,.08)" : "#edf0f5"} />)}
        <polyline fill="none" stroke={BRAND} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" points={points.map((point)=>`${point.x},${point.y}`).join(" ")} />
        {points.map((point)=><circle key={point.label} cx={point.x} cy={point.y} r="5" fill={dark ? "#0b1220" : "#fff"} stroke={BRAND} strokeWidth="3"><title>{point.label}: {point.value}</title></circle>)}
      </svg>
      <div className="-mt-2 flex justify-between px-4 text-[11px]" style={{ color: dark ? "rgba(255,255,255,.55)" : INK_SOFT }}>{labels.map((label)=><span key={label}>{label}</span>)}</div>
    </div>
  );
}

function InsightPanel() {
  return (
    <div
      className="flex flex-col rounded-xl border p-5"
      style={{ borderColor: HAIRLINE, background: "var(--paper-warm)" }}
    >
      <div
        className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase"
        style={{ color: BRAND_DEEP }}
      >
        <ArrowUpRight size={13} /> Actividad fuera de horario
      </div>
      <div
        className="mt-3 text-[19px] font-semibold leading-[1.3]"
        style={{ color: INK }}
      >
        14 gestiones completadas mientras el negocio estaba cerrado.
      </div>
      <p className="mt-3 text-[13.5px] leading-[1.55]" style={{ color: INK_SOFT }}>
        Autogal siguió atendiendo la demanda fuera del horario habitual.
      </p>
      <div className="mt-auto pt-5">
        <div
          className="flex items-center justify-between border-t pt-4 text-[12px]"
          style={{ borderColor: HAIRLINE, color: INK_SOFT }}
        >
          <span>Ver detalle</span>
          <ArrowRight size={14} />
        </div>
      </div>
    </div>
  );
}

/* =====================================================================
   PROBLEM
   ===================================================================== */
function Problem() {
  const events = [
    ["09:42", "Llamada entrante", "recibida"],
    ["09:43", "Consulta resuelta", "gestionada"],
    ["09:44", "Nueva llamada", "recibida"],
    ["09:44", "Llamada simultánea", "recibida"],
    ["09:46", "Reserva gestionada", "gestionada"],
    ["09:48", "Consulta habitual", "gestionada"],
    ["09:51", "Cambio de cita", "gestionada"],
    ["09:53", "Llamada fuera de horario", "gestionada"],
  ];
  return (
    <section id="producto" className="border-t hairline">
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="grid gap-16 lg:grid-cols-[1fr_1.1fr] lg:gap-24">
          <div>
            <div className="eyebrow mb-5">El problema</div>
            <h2
              className="text-display text-[38px] leading-[1.05] lg:text-[52px]"
              style={{ color: INK }}
            >
              La demanda no espera a que puedas responder.
            </h2>
            <p
              className="mt-6 max-w-[520px] text-[18px] leading-[1.55]"
              style={{ color: INK_SOFT }}
            >
              Tu equipo puede estar atendiendo a un cliente, trabajando o
              simplemente fuera del horario habitual. Mientras tanto, el
              teléfono sigue sonando.
            </p>

            <ul className="mt-10 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
              {[
                "Llamadas simultáneas",
                "Horas punta",
                "Fuera de horario",
                "Consultas repetitivas",
                "Reservas, citas y cambios",
                "Solicitudes de información",
              ].map((t) => (
                <li
                  key={t}
                  className="flex items-center gap-3 text-[15px] font-medium"
                  style={{ color: INK }}
                >
                  <span
                    className="h-1 w-1 rounded-full"
                    style={{ background: BRAND }}
                  />
                  {t}
                </li>
              ))}
            </ul>

            <blockquote
              className="mt-12 border-l-2 pl-6 text-[22px] font-semibold leading-[1.35]"
              style={{ borderColor: BRAND, color: INK }}
            >
              No responder una llamada no siempre significa perder una llamada.
              A veces significa perder una oportunidad.
            </blockquote>
          </div>

          <div>
            <div
              className="rounded-2xl border p-2"
              style={{ borderColor: HAIRLINE, background: "#fff" }}
            >
              <div
                className="flex items-center justify-between px-4 py-3 text-[12px]"
                style={{ color: INK_SOFT }}
              >
                <div className="flex items-center gap-2 font-semibold" style={{ color: INK }}>
                  <PhoneIncoming size={14} style={{ color: BRAND }} />
                  Demanda entrante · en vivo
                </div>
                <span className="numeric">08 llamadas · 06 min</span>
              </div>
              <div
                className="rounded-xl px-2 py-2"
                style={{ background: "var(--paper-warm)" }}
              >
                {events.map(([t, l, k], i) => (
                  <div
                    key={i}
                    className="grid grid-cols-[60px_1fr_auto] items-center gap-3 border-b px-3 py-2.5 last:border-b-0"
                    style={{ borderColor: HAIRLINE }}
                  >
                    <span
                      className="numeric text-[12.5px] font-medium"
                      style={{ color: INK_SOFT }}
                    >
                      {t}
                    </span>
                    <span
                      className="text-[14px] font-medium"
                      style={{ color: INK }}
                    >
                      {l}
                    </span>
                    <span
                      className="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                      style={{
                        color: k === "gestionada" ? BRAND_DEEP : INK_SOFT,
                        background:
                          k === "gestionada"
                            ? "var(--brand-soft)"
                            : "transparent",
                        border:
                          k === "gestionada" ? "none" : `1px solid ${HAIRLINE}`,
                      }}
                    >
                      {k === "gestionada" ? "Gestionada" : "Entrante"}
                    </span>
                  </div>
                ))}
              </div>
              <div
                className="flex items-center justify-between px-4 py-3 text-[12px]"
                style={{ color: INK_SOFT }}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: BRAND }}
                  />
                  Autogal está absorbiendo la demanda
                </div>
                <span>Actualizado ahora</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* =====================================================================
   HOW IT WORKS
   ===================================================================== */
function HowItWorks() {
  const stages = [
    {
      n: "01",
      title: "Recibe",
      body: "Autogal atiende la llamada cuando entra.",
    },
    {
      n: "02",
      title: "Gestiona",
      body: "Entiende la solicitud, resuelve consultas y ejecuta las gestiones disponibles.",
    },
    {
      n: "03",
      title: "Resuelve o escala",
      body: "Completa la gestión o deriva la situación cuando necesita atención humana.",
    },
    {
      n: "04",
      title: "Mide",
      body: "La actividad se convierte en información útil para el negocio.",
    },
  ];
  return (
    <section id="como-funciona" className="border-t hairline" style={{ background: "var(--paper-warm)" }}>
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="max-w-[720px]">
          <div className="eyebrow mb-5">Cómo funciona</div>
          <h2
            className="text-display text-[38px] leading-[1.05] lg:text-[52px]"
            style={{ color: INK }}
          >
            Una capa adicional de atención para tu negocio.
          </h2>
        </div>

        <div className="relative mt-16">
          <div
            className="absolute left-0 right-0 top-[38px] hidden h-px lg:block"
            style={{ background: HAIRLINE }}
            aria-hidden
          />
          <div className="grid gap-10 lg:grid-cols-4 lg:gap-6">
            {stages.map((s, i) => (
              <div key={s.n} className="relative">
                <div className="flex items-center gap-3">
                  <div
                    className="numeric text-[13px] font-semibold"
                    style={{ color: BRAND_DEEP }}
                  >
                    {s.n}
                  </div>
                  <div
                    className="h-px flex-1"
                    style={{ background: HAIRLINE }}
                  />
                  <div
                    className="relative z-10 flex h-4 w-4 items-center justify-center rounded-full border-[3px] bg-white"
                    style={{ borderColor: BRAND }}
                  />
                </div>
                <div
                  className="mt-6 text-[22px] font-bold tracking-tight"
                  style={{ color: INK }}
                >
                  {s.title}
                </div>
                <p
                  className="mt-3 max-w-[260px] text-[15px] leading-[1.55]"
                  style={{ color: INK_SOFT }}
                >
                  {s.body}
                </p>
                {i < stages.length - 1 && (
                  <ArrowRight
                    size={16}
                    className="absolute -right-3 top-[30px] hidden lg:block"
                    style={{ color: BRAND }}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* =====================================================================
   CAPABILITIES
   ===================================================================== */
function Capabilities() {
  const caps = [
    { i: PhoneIncoming, t: "Atender llamadas" },
    { i: MessageSquare, t: "Resolver consultas habituales" },
    { i: ClipboardList, t: "Consultar disponibilidad" },
    { i: Calendar, t: "Gestionar reservas y citas" },
    { i: Repeat, t: "Gestionar cambios" },
    { i: Moon, t: "Atender fuera de horario" },
    { i: UserRoundCheck, t: "Detectar situaciones que requieren atención humana" },
    { i: BarChart3, t: "Registrar actividad operativa" },
  ];
  return (
    <section className="border-t hairline">
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="max-w-[820px]">
          <div className="eyebrow mb-5">Capacidades</div>
          <h2
            className="text-display text-[38px] leading-[1.05] lg:text-[52px]"
            style={{ color: INK }}
          >
            Más capacidad de atención.{" "}
            <span style={{ color: INK_SOFT }}>Menos demanda sin responder.</span>
          </h2>
        </div>
        <div
          className="mt-14 grid grid-cols-1 border-t sm:grid-cols-2 lg:grid-cols-4"
          style={{ borderColor: HAIRLINE }}
        >
          {caps.map((c, i) => (
            <div
              key={c.t}
              className="border-b p-6 lg:p-7"
              style={{
                borderColor: HAIRLINE,
                borderRightWidth: (i + 1) % 4 === 0 ? 0 : undefined,
              }}
            >
              <div
                className="mb-4 flex h-9 w-9 items-center justify-center rounded-md"
                style={{ background: "var(--brand-soft)", color: BRAND_DEEP }}
              >
                <c.i size={18} strokeWidth={1.75} />
              </div>
              <div
                className="text-[15.5px] font-semibold leading-[1.4]"
                style={{ color: INK }}
              >
                {c.t}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* =====================================================================
   MULTI-INDUSTRY
   ===================================================================== */
const SECTORS = [
  {
    k: "clinicas",
    label: "Clínicas",
    items: ["Consultas frecuentes", "Citas", "Cambios de cita", "Disponibilidad"],
  },
  {
    k: "belleza",
    label: "Belleza",
    items: ["Servicios", "Reservas", "Disponibilidad", "Cambios de hora"],
  },
  {
    k: "veterinaria",
    label: "Veterinaria",
    items: ["Consultas", "Citas", "Disponibilidad", "Derivación"],
  },
  {
    k: "talleres",
    label: "Talleres",
    items: [
      "Solicitudes",
      "Información",
      "Disponibilidad",
      "Seguimiento inicial",
    ],
  },
  {
    k: "servicios",
    label: "Servicios profesionales",
    items: ["Consultas", "Citas", "Disponibilidad", "Derivación"],
  },
  {
    k: "otros",
    label: "Otros negocios de servicios",
    items: [
      "Solicitudes",
      "Información",
      "Reservas",
      "Seguimiento",
    ],
  },
];

function Industries() {
  const [active, setActive] = useState("clinicas");
  const s = SECTORS.find((x) => x.k === active)!;
  return (
    <section id="soluciones" className="border-t hairline" style={{ background: "var(--paper-warm)" }}>
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="max-w-[820px]">
          <div className="eyebrow mb-5">Soluciones</div>
          <h2
            className="text-display text-[38px] leading-[1.05] lg:text-[52px]"
            style={{ color: INK }}
          >
            Distintos negocios. El mismo problema: la demanda sigue entrando.
          </h2>
        </div>

        <div className="mt-12 flex flex-wrap gap-2">
          {SECTORS.map((sec) => {
            const on = sec.k === active;
            return (
              <button
                key={sec.k}
                onClick={() => setActive(sec.k)}
                className="rounded-full border px-4 py-2 text-[13.5px] font-medium transition-colors"
                style={{
                  borderColor: on ? INK : HAIRLINE,
                  background: on ? INK : "#fff",
                  color: on ? "var(--paper)" : INK,
                }}
              >
                {sec.label}
              </button>
            );
          })}
        </div>

        <div
          className="mt-10 grid gap-0 rounded-2xl border bg-white lg:grid-cols-[1fr_1.4fr]"
          style={{ borderColor: HAIRLINE }}
        >
          <div className="p-8 lg:p-10">
            <div
              className="text-[11px] font-semibold uppercase tracking-[0.14em]"
              style={{ color: BRAND_DEEP }}
            >
              {s.label}
            </div>
            <div
              className="mt-3 text-[26px] font-bold leading-[1.15] tracking-tight"
              style={{ color: INK }}
            >
              Autogal adapta la lógica operativa al negocio.
            </div>
            <p
              className="mt-4 text-[15px] leading-[1.55]"
              style={{ color: INK_SOFT }}
            >
              Cada sector recibe una demanda distinta. La plataforma se
              configura sobre las gestiones más frecuentes de tu operativa
              real.
            </p>
          </div>
          <div
            className="border-t p-8 lg:border-t-0 lg:border-l lg:p-10"
            style={{ borderColor: HAIRLINE }}
          >
            <div
              className="text-[12px] font-semibold uppercase tracking-[0.14em]"
              style={{ color: INK_SOFT }}
            >
              Casos operativos
            </div>
            <ul className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {s.items.map((it) => (
                <li
                  key={it}
                  className="flex items-center gap-3 rounded-lg border px-4 py-3 text-[14.5px] font-medium"
                  style={{ borderColor: HAIRLINE, color: INK }}
                >
                  <Check size={15} style={{ color: BRAND }} strokeWidth={2.5} />
                  {it}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

/* =====================================================================
   BUSINESS INTELLIGENCE
   ===================================================================== */
function BusinessIntelligence() {
  return (
    <section id="resultados" className="border-t hairline">
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr] lg:items-end">
          <div>
            <div className="eyebrow mb-5">Business intelligence</div>
            <h2
              className="text-display text-[38px] leading-[1.05] lg:text-[52px]"
              style={{ color: INK }}
            >
              No solo atiende.
              <br />
              <span style={{ color: INK_SOFT }}>Te muestra qué está ocurriendo.</span>
            </h2>
          </div>
          <p
            className="max-w-[520px] text-[17px] leading-[1.55] lg:justify-self-end"
            style={{ color: INK_SOFT }}
          >
            Convierte la actividad telefónica en información clara para
            entender la demanda, detectar patrones y descubrir oportunidades.
          </p>
        </div>

        {/* Metrics row */}
        <div
          className="mt-14 grid grid-cols-2 border-y lg:grid-cols-4"
          style={{ borderColor: HAIRLINE }}
        >
          {[
            ["327", "Llamadas gestionadas"],
            ["64", "Reservas y citas gestionadas"],
            ["82 %", "Resolución autónoma"],
            ["14", "Gestiones fuera de horario"],
          ].map(([v, l], i) => (
            <div
              key={l}
              className={`px-6 py-8 lg:px-8 ${i > 0 ? "lg:border-l" : ""} ${
                i === 2 ? "border-t lg:border-t-0" : ""
              } ${i === 3 ? "border-t lg:border-t-0" : ""}`}
              style={{ borderColor: HAIRLINE }}
            >
              <div
                className="numeric text-[46px] font-bold leading-none tracking-[-0.03em] lg:text-[56px]"
                style={{ color: INK }}
              >
                {v}
              </div>
              <div
                className="mt-3 text-[13.5px] font-medium"
                style={{ color: INK_SOFT }}
              >
                {l}
              </div>
            </div>
          ))}
        </div>

        {/* Charts grid */}
        <div className="mt-10 grid gap-6 lg:grid-cols-6">
          <div
            className="rounded-2xl border p-6 lg:col-span-4"
            style={{ borderColor: HAIRLINE, background: "#fff" }}
          >
            <ChartHeader
              title="Llamadas gestionadas"
              subtitle="Últimos 6 meses"
            />
            <div className="mt-4 h-[260px]">
              <CallsLineChart />
            </div>
          </div>

          <div
            className="rounded-2xl border p-6 lg:col-span-2"
            style={{ borderColor: HAIRLINE, background: "#fff" }}
          >
            <ChartHeader title="Resultado de las llamadas" />
            <div className="mt-4 flex items-center justify-center">
              <div className="relative h-[180px] w-[180px]">
                <div
                  className="h-full w-full rounded-full"
                  role="img"
                  aria-label="Distribución de resultados de llamada"
                  style={{
                    background: `conic-gradient(${BRAND} 0 42%, ${BRAND_DEEP} 42% 70%, oklch(0.72 0.06 245) 70% 84%, oklch(0.86 0.02 245) 84% 94%, oklch(0.92 0.01 245) 94% 100%)`,
                    WebkitMask: "radial-gradient(circle, transparent 0 52%, #000 53%)",
                    mask: "radial-gradient(circle, transparent 0 52%, #000 53%)",
                  }}
                />
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <div
                    className="numeric text-[26px] font-bold leading-none"
                    style={{ color: INK }}
                  >
                    82 %
                  </div>
                  <div
                    className="mt-1 text-[11px] font-medium"
                    style={{ color: INK_SOFT }}
                  >
                    resolución
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-4 space-y-1.5">
              {[
                ["Resueltas", 42, BRAND],
                ["Gestiones completadas", 28, BRAND_DEEP],
                ["Transferidas", 14, "oklch(0.72 0.06 245)"],
                ["Sin acción", 10, "oklch(0.86 0.02 245)"],
                ["Fallidas", 6, "oklch(0.92 0.01 245)"],
              ].map(([l, v, c]) => (
                <div key={l as string} className="flex items-center gap-2 text-[12.5px]">
                  <span
                    className="h-2 w-2 rounded-sm"
                    style={{ background: c as string }}
                  />
                  <span className="flex-1" style={{ color: INK_SOFT }}>
                    {l as string}
                  </span>
                  <span className="numeric font-semibold" style={{ color: INK }}>
                    {v as number} %
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="rounded-2xl border p-6 lg:col-span-3"
            style={{ borderColor: HAIRLINE, background: "#fff" }}
          >
            <ChartHeader title="Demanda por servicio" />
            <div className="mt-4 h-[220px]">
              <div className="space-y-4 pt-2" role="img" aria-label="Demanda por servicio">
                {[
                  ["Servicio principal", 31],
                  ["Servicio recurrente", 18],
                  ["Consulta", 9],
                  ["Otra gestión", 6],
                ].map(([label, value], index) => (
                  <div key={String(label)} className="grid grid-cols-[9rem_1fr_2rem] items-center gap-3 text-[12px]">
                    <span className="truncate" style={{ color: INK }}>{label}</span>
                    <div className="h-4 overflow-hidden rounded-sm" style={{ background: HAIRLINE }}>
                      <div className="h-full rounded-sm" style={{ width: `${(Number(value) / 31) * 100}%`, background: [BRAND, "oklch(0.62 0.10 245)", "oklch(0.75 0.06 245)", "oklch(0.86 0.03 245)"][index] }} />
                    </div>
                    <strong className="numeric" style={{ color: INK }}>{value}</strong>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div
            className="rounded-2xl border p-6 lg:col-span-3"
            style={{ borderColor: HAIRLINE, background: "#fff" }}
          >
            <ChartHeader title="Momentos de mayor demanda" />
            <Heatmap />
          </div>
        </div>

        {/* Insights */}
        <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {[
            [
              "Demanda",
              "El 38 % de las llamadas se concentra entre las 10:00 y las 12:00.",
            ],
            [
              "Tendencia",
              "La demanda del servicio principal ha crecido un 24 %.",
            ],
            [
              "Fuera de horario",
              "14 gestiones se completaron fuera del horario habitual.",
            ],
            [
              "Actividad",
              "Los lunes recibes un 26 % más de llamadas que la media semanal.",
            ],
          ].map(([label, body]) => (
            <div key={label} className="border-t pt-5" style={{ borderColor: HAIRLINE }}>
              <div
                className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em]"
                style={{ color: BRAND_DEEP }}
              >
                <ArrowUpRight size={13} /> {label}
              </div>
              <div
                className="mt-3 text-[16px] font-semibold leading-[1.4]"
                style={{ color: INK }}
              >
                {body}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ChartHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex items-start justify-between">
      <div>
        <div className="text-[13px] font-semibold" style={{ color: INK }}>
          {title}
        </div>
        {subtitle && (
          <div className="text-[12px]" style={{ color: INK_SOFT }}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
}

function Heatmap() {
  const days = ["L", "M", "X", "J", "V"];
  const hours = ["09", "10", "11", "12", "13", "16", "17"];
  // deterministic values 0..4
  const data = [
    [1, 2, 3, 4, 3, 2, 2],
    [2, 3, 4, 4, 3, 2, 3],
    [1, 3, 3, 4, 2, 2, 2],
    [2, 3, 4, 3, 3, 3, 3],
    [1, 2, 3, 3, 2, 1, 1],
  ];
  const shade = (v: number) => {
    const alphas = [0.06, 0.18, 0.36, 0.6, 0.85];
    return `color-mix(in oklab, ${BRAND} ${alphas[v] * 100}%, transparent)`;
  };
  return (
    <div className="mt-4">
      <div className="grid grid-cols-[24px_repeat(7,1fr)] gap-1.5">
        <div />
        {hours.map((h) => (
          <div
            key={h}
            className="text-center text-[10.5px] font-medium"
            style={{ color: INK_SOFT }}
          >
            {h}
          </div>
        ))}
        {days.map((d, ri) => (
          <Fragment key={d}>
            <div
              className="flex items-center text-[11px] font-semibold"
              style={{ color: INK_SOFT }}
            >
              {d}
            </div>
            {data[ri].map((v, ci) => (
              <div
                key={`${d}-${ci}`}
                className="h-8 rounded-md border"
                style={{
                  background: shade(v),
                  borderColor: HAIRLINE,
                }}
              />
            ))}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

/* =====================================================================
   AFTER HOURS
   ===================================================================== */
function AfterHours() {
  return (
    <section
      className="relative overflow-hidden border-t"
      style={{ background: "var(--night)", borderColor: "rgba(255,255,255,0.06)" }}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          background:
            "radial-gradient(600px 300px at 20% 20%, color-mix(in oklab, oklch(0.52 0.13 245) 30%, transparent), transparent 60%), radial-gradient(500px 260px at 90% 80%, color-mix(in oklab, oklch(0.52 0.13 245) 18%, transparent), transparent 60%)",
        }}
      />
      <div className="relative mx-auto max-w-[1320px] px-6 py-24 text-white lg:px-10 lg:py-32">
        <div className="grid gap-14 lg:grid-cols-[1.05fr_1fr] lg:gap-20">
          <div>
            <div
              className="mb-5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em]"
              style={{ color: "oklch(0.85 0.06 240)" }}
            >
              <Moon size={13} /> Fuera de horario
            </div>
            <h2 className="text-display text-[38px] leading-[1.05] lg:text-[52px]">
              Tu horario termina.
              <br />
              <span style={{ color: "rgba(255,255,255,0.55)" }}>
                La demanda no siempre.
              </span>
            </h2>
            <p
              className="mt-6 max-w-[520px] text-[17px] leading-[1.55]"
              style={{ color: "rgba(255,255,255,0.65)" }}
            >
              Autogal puede mantener una capa de atención activa cuando tu
              equipo no está disponible.
            </p>

            <div className="mt-12 flex items-baseline gap-4">
              <div className="numeric text-[92px] font-bold leading-none tracking-[-0.04em] lg:text-[128px]">
                14
              </div>
              <div className="max-w-[220px] pb-3 text-[14px]" style={{ color: "rgba(255,255,255,0.6)" }}>
                Gestiones completadas fuera de horario
              </div>
            </div>
          </div>

          <div>
            <DayTimeline />
            <div className="mt-8 space-y-3">
              {[
                ["20:42", "Consulta resuelta"],
                ["21:18", "Reserva gestionada"],
                ["07:34", "Solicitud registrada"],
              ].map(([t, l]) => (
                <div
                  key={t}
                  className="flex items-center justify-between rounded-lg border px-4 py-3"
                  style={{
                    borderColor: "rgba(255,255,255,0.08)",
                    background: "rgba(255,255,255,0.02)",
                  }}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ background: BRAND }}
                    />
                    <span
                      className="numeric text-[13px] font-medium"
                      style={{ color: "rgba(255,255,255,0.6)" }}
                    >
                      {t}
                    </span>
                    <span className="text-[14.5px] font-medium">{l}</span>
                  </div>
                  <span
                    className="text-[11.5px] font-semibold"
                    style={{ color: "oklch(0.85 0.06 240)" }}
                  >
                    Gestionada
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function DayTimeline() {
  // 4 segments across 24h
  const segs = [
    { from: 0, to: 8, off: true, label: "Fuera de horario" },
    { from: 8, to: 14, off: false, label: "Equipo disponible" },
    { from: 14, to: 16, off: true, label: "Fuera de horario" },
    { from: 16, to: 20, off: false, label: "Equipo disponible" },
    { from: 20, to: 24, off: true, label: "Fuera de horario" },
  ];
  return (
    <div>
      <div className="mb-3 flex items-center justify-between text-[11px]" style={{ color: "rgba(255,255,255,0.5)" }}>
        <span>00:00</span>
        <span>12:00</span>
        <span>24:00</span>
      </div>
      <div
        className="relative h-14 overflow-hidden rounded-lg border"
        style={{ borderColor: "rgba(255,255,255,0.08)" }}
      >
        {segs.map((s, i) => {
          const w = ((s.to - s.from) / 24) * 100;
          const left = (s.from / 24) * 100;
          return (
            <div
              key={i}
              className="absolute inset-y-0 flex items-center justify-center text-[10.5px] font-medium"
              style={{
                left: `${left}%`,
                width: `${w}%`,
                background: s.off
                  ? "color-mix(in oklab, oklch(0.52 0.13 245) 22%, transparent)"
                  : "rgba(255,255,255,0.04)",
                borderRight:
                  i < segs.length - 1 ? "1px solid rgba(255,255,255,0.1)" : "none",
                color: s.off ? "oklch(0.9 0.05 240)" : "rgba(255,255,255,0.55)",
              }}
            >
              {w > 10 ? s.label : ""}
            </div>
          );
        })}
        {/* activity ticks */}
        {[20.7, 21.3, 7.5].map((h) => (
          <div
            key={h}
            className="absolute top-1 h-3 w-px"
            style={{
              left: `${(h / 24) * 100}%`,
              background: BRAND,
            }}
          />
        ))}
      </div>
    </div>
  );
}

/* =====================================================================
   TEAM
   ===================================================================== */
function Team() {
  return (
    <section className="border-t hairline">
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="grid gap-14 lg:grid-cols-[1fr_1.1fr] lg:gap-20">
          <div>
            <div className="eyebrow mb-5">Equipo</div>
            <h2
              className="text-display text-[38px] leading-[1.05] lg:text-[52px]"
              style={{ color: INK }}
            >
              No sustituye a tu equipo.{" "}
              <span style={{ color: INK_SOFT }}>Amplía su capacidad.</span>
            </h2>
            <p
              className="mt-6 max-w-[520px] text-[17px] leading-[1.55]"
              style={{ color: INK_SOFT }}
            >
              Las personas siguen ocupándose de los clientes y de las
              situaciones que necesitan criterio humano. Autogal absorbe parte
              de la presión telefónica y mantiene una capa adicional de
              atención.
            </p>
          </div>

          <RoutingDiagram />
        </div>
      </div>
    </section>
  );
}

function RoutingDiagram() {
  return (
    <div
      className="rounded-2xl border p-8 lg:p-10"
      style={{ borderColor: HAIRLINE, background: "var(--paper-warm)" }}
    >
      <div className="flex flex-col items-center">
        <NodePill label="Demanda entrante" muted />
        <Connector />
        <NodePill label="Autogal" primary />
        <div className="relative mt-4 flex w-full max-w-[420px] items-start justify-between">
          <svg className="pointer-events-none absolute -top-4 left-1/2 -translate-x-1/2" width="220" height="34" viewBox="0 0 220 34" fill="none">
            <path d="M110 0 L20 34" stroke={BRAND} strokeWidth="1.5" />
            <path d="M110 0 L200 34" stroke={BRAND} strokeWidth="1.5" />
          </svg>
          <div className="pt-8">
            <NodePill label="Gestión automática" small />
          </div>
          <div className="pt-8">
            <NodePill label="Equipo humano" small />
          </div>
        </div>
      </div>
    </div>
  );
}

function NodePill({
  label,
  primary,
  muted,
  small,
}: {
  label: string;
  primary?: boolean;
  muted?: boolean;
  small?: boolean;
}) {
  return (
    <div
      className={`rounded-full border font-semibold ${
        small ? "px-4 py-2 text-[12.5px]" : "px-6 py-3 text-[14.5px]"
      }`}
      style={{
        background: primary ? INK : "#fff",
        color: primary ? "var(--paper)" : muted ? INK_SOFT : INK,
        borderColor: primary ? INK : HAIRLINE,
      }}
    >
      {label}
    </div>
  );
}

function Connector() {
  return (
    <div className="my-3 flex flex-col items-center">
      <div className="h-6 w-px" style={{ background: HAIRLINE }} />
      <div className="h-1.5 w-1.5 rounded-full" style={{ background: BRAND }} />
    </div>
  );
}

/* =====================================================================
   CTA
   ===================================================================== */
function CTA() {
  return (
    <section
      id="cta"
      className="border-t hairline"
      style={{ background: "var(--paper-warm)" }}
    >
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="mx-auto max-w-[820px] text-center">
          <div className="eyebrow mb-5">Empezar</div>
          <h2
            className="text-display text-[40px] leading-[1.05] lg:text-[60px]"
            style={{ color: INK }}
          >
            Descubre qué podría gestionar Autogal en tu negocio.
          </h2>
          <p
            className="mx-auto mt-6 max-w-[620px] text-[18px] leading-[1.55]"
            style={{ color: INK_SOFT }}
          >
            Cuéntanos cómo recibes y gestionas tus llamadas. Te enseñaremos
            cómo encajaría Autogal en tu operativa.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-5">
            <a href="https://client.autogal.es/register" className="btn-primary">
              Registrarse <ArrowRight size={16} />
            </a>
            <a
              href="#"
              className="inline-flex items-center gap-2 text-[15px] font-semibold underline-offset-4 hover:underline"
              style={{ color: INK }}
            >
              Hablar con nosotros
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

/* =====================================================================
   FAQ
   ===================================================================== */
const FAQS: Array<[string, string]> = [
  [
    "¿Autogal sustituye a mi equipo?",
    "No. Autogal está pensado para trabajar junto a tu equipo. Absorbe parte de la demanda telefónica que no llegáis a atender y deriva las situaciones que requieren criterio humano.",
  ],
  [
    "¿Qué tipo de llamadas puede gestionar?",
    "Consultas habituales, información sobre servicios, comprobación de disponibilidad, reservas o citas y algunos cambios sencillos. La configuración se adapta a la operativa real de cada negocio.",
  ],
  [
    "¿Puede gestionar reservas o citas?",
    "Sí, cuando existe una integración disponible con el sistema del negocio. Autogal comprueba disponibilidad y ejecuta la gestión dentro de los límites que se hayan definido.",
  ],
  [
    "¿Qué ocurre cuando una llamada necesita atención humana?",
    "Autogal detecta esas situaciones y las deriva al equipo, dejando registro de lo que ha ocurrido y del contexto de la llamada.",
  ],
  [
    "¿Puede atender fuera del horario habitual?",
    "Sí. Autogal puede mantener una capa de atención activa cuando el negocio está cerrado o el equipo no está disponible.",
  ],
  [
    "¿Puedo consultar la actividad de las llamadas?",
    "Sí. La actividad telefónica se convierte en información operativa: volumen, resultados, momentos de mayor demanda y patrones útiles para la gestión del negocio.",
  ],
  [
    "¿Autogal funciona igual para todos los negocios?",
    "La plataforma es la misma. La lógica operativa se ajusta a cada tipo de negocio y a las gestiones concretas que se quieran cubrir.",
  ],
];

function FAQ() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <section id="faq" className="border-t hairline">
      <div className="mx-auto max-w-[1320px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="grid gap-14 lg:grid-cols-[1fr_1.4fr] lg:gap-20">
          <div>
            <div className="eyebrow mb-5">FAQ</div>
            <h2
              className="text-display text-[38px] leading-[1.05] lg:text-[48px]"
              style={{ color: INK }}
            >
              Preguntas frecuentes.
            </h2>
          </div>
          <div className="border-t" style={{ borderColor: HAIRLINE }}>
            {FAQS.map(([q, a], i) => {
              const isOpen = open === i;
              return (
                <div
                  key={q}
                  className="border-b"
                  style={{ borderColor: HAIRLINE }}
                >
                  <button
                    className="flex w-full items-start justify-between gap-6 py-6 text-left"
                    onClick={() => setOpen(isOpen ? null : i)}
                  >
                    <span
                      className="text-[17px] font-semibold leading-[1.45]"
                      style={{ color: INK }}
                    >
                      {q}
                    </span>
                    <span
                      className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border"
                      style={{ borderColor: HAIRLINE, color: INK }}
                    >
                      {isOpen ? <Minus size={13} /> : <Plus size={13} />}
                    </span>
                  </button>
                  {isOpen && (
                    <div
                      className="pb-6 pr-10 text-[15.5px] leading-[1.6]"
                      style={{ color: INK_SOFT }}
                    >
                      {a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

/* =====================================================================
   FOOTER
   ===================================================================== */
function Footer() {
  return (
    <footer className="border-t hairline">
      <div className="mx-auto max-w-[1320px] px-6 py-14 lg:px-10">
        <div className="flex flex-col justify-between gap-10 lg:flex-row lg:items-end">
          <div>
            <Wordmark />
            <p
              className="mt-4 max-w-[380px] text-[13.5px] leading-[1.55]"
              style={{ color: INK_SOFT }}
            >
              Plataforma inteligente de operaciones telefónicas para negocios
              de servicio.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-14 gap-y-3 text-[13.5px] sm:grid-cols-3">
            {[
              ["Producto", "#producto"],
              ["Cómo funciona", "#como-funciona"],
              ["Soluciones", "#soluciones"],
              ["Resultados", "#resultados"],
              ["Preguntas frecuentes", "#faq"],
              ["Acceder", "/auth/login/google/start?portal=client&return_to=/"],
            ].map(([l, href]) => (
              <a key={l} href={href} style={{ color: INK }} className="font-medium hover:underline">
                {l}
              </a>
            ))}
          </div>
        </div>
        <div
          className="mt-10 flex flex-col justify-between gap-4 border-t pt-6 text-[12.5px] sm:flex-row"
          style={{ borderColor: HAIRLINE, color: INK_SOFT }}
        >
          <div>© Autogal</div>
          <div className="flex gap-6">
            <a href="/aviso-legal" className="hover:underline">
              Aviso legal
            </a>
            <a href="/privacidad" className="hover:underline">
              Privacidad
            </a>
            <a href="/cookies" className="hover:underline">
              Cookies
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}

/* =====================================================================
   PAGE
   ===================================================================== */
export default function App() {
  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <StyleTag />
      <Nav />
      <main>
        <Hero />
        <Problem />
        <HowItWorks />
        <Capabilities />
        <Industries />
        <BusinessIntelligence />
        <AfterHours />
        <Team />
        <CTA />
        <FAQ />
      </main>
      <Footer />
    </div>
  );
}

function StyleTag() {
  const ref = useRef<HTMLStyleElement>(null);
  return (
    <style ref={ref}>{`
      .btn-primary {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: ${INK};
        color: var(--paper);
        font-weight: 600;
        font-size: 14.5px;
        padding: 12px 20px;
        border-radius: 10px;
        transition: transform 0.15s ease, background 0.2s ease;
      }
      .btn-primary:hover {
        background: ${BRAND_DEEP};
      }
      .btn-primary:active { transform: translateY(1px); }
    `}</style>
  );
}
