import type { ReactNode } from "react";

type ChartPoint = { label: string; value: number };

const formatValue = (value: number) => new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 }).format(value);

export function BarChart({ data, valueSuffix = "" }: { data: ChartPoint[]; valueSuffix?: string }) {
  const max = Math.max(1, ...data.map((item) => item.value));
  if (!data.length) return <EmptyChart />;
  return (
    <div className="space-y-3" role="img" aria-label="Gráfico de barras">
      {data.map((item) => (
        <div key={item.label} className="grid grid-cols-[minmax(7rem,1fr)_3fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-[#4d596d]" title={item.label}>{item.label}</span>
          <div className="h-3 overflow-hidden rounded-full bg-[#edf1f7]">
            <div className="h-full rounded-full bg-[#315efb]" style={{ width: `${Math.max(2, (item.value / max) * 100)}%` }} />
          </div>
          <span className="tabular-nums font-semibold text-[#19243b]">{formatValue(item.value)}{valueSuffix}</span>
        </div>
      ))}
    </div>
  );
}

export function LineChart({ data }: { data: ChartPoint[] }) {
  if (!data.length) return <EmptyChart />;
  const width = 720;
  const height = 240;
  const padding = 28;
  const max = Math.max(1, ...data.map((item) => item.value));
  const points = data.map((item, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(1, data.length - 1);
    const y = height - padding - (item.value / max) * (height - padding * 2);
    return { ...item, x, y };
  });
  return (
    <div className="overflow-x-auto" role="img" aria-label="Gráfico temporal">
      <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[36rem] w-full" aria-hidden="true">
        <line x1={padding} y1={height-padding} x2={width-padding} y2={height-padding} stroke="#d9e0ec" />
        <polyline fill="none" stroke="#315efb" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" points={points.map((point) => `${point.x},${point.y}`).join(" ")} />
        {points.map((point) => <circle key={`${point.label}-${point.x}`} cx={point.x} cy={point.y} r="5" fill="#fff" stroke="#315efb" strokeWidth="3"><title>{point.label}: {formatValue(point.value)}</title></circle>)}
      </svg>
      <div className="mt-2 flex justify-between gap-4 text-xs text-[#7b8799]">
        <span>{data[0]?.label}</span><span>{data.at(-1)?.label}</span>
      </div>
    </div>
  );
}

export function DonutChart({ data, centerLabel }: { data: ChartPoint[]; centerLabel?: ReactNode }) {
  const total = data.reduce((sum, item) => sum + Math.max(0, item.value), 0);
  if (!data.length || total === 0) return <EmptyChart />;
  const palette = ["#315efb", "#22a06b", "#f59e0b", "#7650c8", "#e5484d", "#0ea5e9"];
  let offset = 0;
  const segments = data.map((item, index) => {
    const start = offset;
    const portion = (Math.max(0, item.value) / total) * 100;
    offset += portion;
    return `${palette[index % palette.length]} ${start}% ${offset}%`;
  });
  return (
    <div className="grid gap-5 sm:grid-cols-[12rem_1fr] sm:items-center" role="img" aria-label="Gráfico de distribución">
      <div className="relative mx-auto size-44 rounded-full" style={{ background: `conic-gradient(${segments.join(",")})` }}>
        <div className="absolute inset-7 grid place-items-center rounded-full bg-white text-center text-sm font-semibold text-[#19243b]">{centerLabel ?? formatValue(total)}</div>
      </div>
      <div className="space-y-2">
        {data.map((item,index)=><div key={item.label} className="flex items-center justify-between gap-3 text-sm"><span className="flex min-w-0 items-center gap-2"><i className="size-2.5 shrink-0 rounded-full" style={{background:palette[index%palette.length]}}/><span className="truncate">{item.label}</span></span><strong className="tabular-nums">{formatValue(item.value)}</strong></div>)}
      </div>
    </div>
  );
}

export function Heatmap({ data }: { data: Array<{ day: string; hour: string; value: number }> }) {
  if (!data.length) return <EmptyChart />;
  const max = Math.max(1, ...data.map((item) => item.value));
  return <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 md:grid-cols-8" role="img" aria-label="Mapa de calor por día y hora">{data.map((item)=><div key={`${item.day}-${item.hour}`} className="rounded-lg border p-2 text-center text-xs" style={{backgroundColor:`rgba(49,94,251,${0.08 + (item.value/max)*0.72})`}} title={`${item.day} ${item.hour}: ${item.value}`}><div className="font-medium">{item.day}</div><div>{item.hour}</div><strong>{item.value}</strong></div>)}</div>;
}

export function FunnelChart({ data }: { data: ChartPoint[] }) {
  const max = Math.max(1, ...data.map((item) => item.value));
  if (!data.length) return <EmptyChart />;
  return <div className="space-y-2" role="img" aria-label="Embudo de conversión">{data.map((item,index)=><div key={item.label} className="mx-auto rounded-lg bg-[#315efb] px-3 py-2 text-center text-sm font-semibold text-white" style={{width:`${Math.max(30,(item.value/max)*100)}%`,opacity:1-index*0.15}}>{item.label}: {formatValue(item.value)}</div>)}</div>;
}

function EmptyChart() { return <div className="grid min-h-40 place-items-center rounded-xl border border-dashed text-sm text-[#7b8799]">Todavía no hay datos para este periodo.</div>; }
