"use client";

import { useId, useMemo, useState } from "react";

import { date, dt } from "@/lib/format";

type Point = [number, number];

function extent(values: number[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!Number.isFinite(lo)) return [0, 1];
  if (lo === hi) return [lo - 1, hi + 1];
  const pad = (hi - lo) * 0.06;
  return [lo - pad, hi + pad];
}

/** Time series chart (SVG). `kind="area-negative"` draws a drawdown area below zero. */
export function SeriesChart({
  points,
  height = 220,
  kind = "line",
  format,
  label,
  baseline,
}: {
  points: Point[];
  height?: number;
  kind?: "line" | "area-negative";
  format: (v: number) => string;
  label: string;
  baseline?: number;
}) {
  const gid = useId();
  const [hover, setHover] = useState<number | null>(null);
  const W = 800;
  const H = height;
  const padL = 4;
  const padR = 84;
  const padT = 8;
  const padB = 20;
  const geo = useMemo(() => {
    if (points.length < 2) return null;
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    const [y0, y1] = kind === "area-negative" ? [Math.min(...ys, 0) * 1.05 || -0.01, 0] : extent(baseline !== undefined ? [...ys, baseline] : ys);
    const x0 = xs[0];
    const x1 = xs[xs.length - 1];
    const sx = (x: number) => padL + ((x - x0) / (x1 - x0 || 1)) * (W - padL - padR);
    const sy = (y: number) => padT + (1 - (y - y0) / (y1 - y0 || 1)) * (H - padT - padB);
    const d = points.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => y0 + (y1 - y0) * t);
    return { sx, sy, d, ticks, x0, x1, y0, y1 };
  }, [points, kind, baseline, H]);

  if (!geo) return <div className="flex h-24 items-center justify-center text-xs text-fg-faint">Not enough data to draw {label.toLowerCase()}.</div>;
  const color = kind === "area-negative" ? "var(--color-negative)" : "var(--color-accent)";
  const hp = hover !== null ? points[hover] : null;

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    const t = geo!.x0 + ((x - padL) / (W - padL - padR)) * (geo!.x1 - geo!.x0);
    let lo = 0;
    let hi = points.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (points[mid][0] < t) lo = mid;
      else hi = mid;
    }
    setHover(Math.abs(points[lo][0] - t) < Math.abs(points[hi][0] - t) ? lo : hi);
  }

  return (
    <figure className="relative" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={label} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <defs>
          <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={kind === "area-negative" ? 0.05 : 0.18} />
            <stop offset="100%" stopColor={color} stopOpacity={kind === "area-negative" ? 0.28 : 0} />
          </linearGradient>
        </defs>
        {geo.ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={geo.sy(t)} y2={geo.sy(t)} stroke="var(--color-line)" strokeWidth={1} />
            <text x={W - padR + 6} y={geo.sy(t) + 3} fontSize={10} fill="var(--color-fg-faint)" className="num">
              {format(t)}
            </text>
          </g>
        ))}
        {baseline !== undefined && (
          <line x1={padL} x2={W - padR} y1={geo.sy(baseline)} y2={geo.sy(baseline)} stroke="var(--color-fg-faint)" strokeDasharray="4 4" strokeWidth={1} />
        )}
        <path
          d={`${geo.d}L${geo.sx(geo.x1).toFixed(1)},${geo.sy(kind === "area-negative" ? 0 : geo.y0).toFixed(1)}L${geo.sx(geo.x0).toFixed(1)},${geo.sy(kind === "area-negative" ? 0 : geo.y0).toFixed(1)}Z`}
          fill={`url(#${gid})`}
        />
        <path d={geo.d} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        <text x={padL} y={H - 5} fontSize={10} fill="var(--color-fg-faint)">
          {date(geo.x0)}
        </text>
        <text x={W - padR} y={H - 5} fontSize={10} fill="var(--color-fg-faint)" textAnchor="end">
          {date(geo.x1)}
        </text>
        {hp && (
          <g>
            <line x1={geo.sx(hp[0])} x2={geo.sx(hp[0])} y1={padT} y2={H - padB} stroke="var(--color-fg-faint)" strokeWidth={1} />
            <circle cx={geo.sx(hp[0])} cy={geo.sy(hp[1])} r={3} fill={color} />
          </g>
        )}
      </svg>
      {hp && (
        <div className="pointer-events-none absolute left-2 top-2 rounded-sm border border-line bg-panel/95 px-2 py-1 text-xs">
          <span className="text-fg-faint">{dt(hp[0])}</span> <span className="num ml-1">{format(hp[1])}</span>
        </div>
      )}
    </figure>
  );
}

/** Compact candlestick chart for data previews. rows: [open_time, open, high, low, close, volume]. */
export function Candles({ rows, height = 240 }: { rows: number[][]; height?: number }) {
  const W = 800;
  const H = height;
  if (rows.length < 2) return <div className="text-xs text-fg-faint">No candles.</div>;
  const [lo, hi] = extent(rows.flatMap((r) => [r[2], r[3]]));
  const bw = (W - 60) / rows.length;
  const sy = (v: number) => 6 + (1 - (v - lo) / (hi - lo)) * (H - 26);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Candlestick preview">
      {[0, 0.5, 1].map((t, i) => {
        const v = lo + (hi - lo) * t;
        return (
          <g key={i}>
            <line x1={0} x2={W - 60} y1={sy(v)} y2={sy(v)} stroke="var(--color-line)" />
            <text x={W - 54} y={sy(v) + 3} fontSize={10} fill="var(--color-fg-faint)" className="num">
              {v.toFixed(v > 100 ? 0 : 2)}
            </text>
          </g>
        );
      })}
      {rows.map((r, i) => {
        const up = r[4] >= r[1];
        const x = i * bw + bw / 2;
        const c = up ? "var(--color-accent)" : "var(--color-negative)";
        return (
          <g key={r[0]}>
            <line x1={x} x2={x} y1={sy(r[2])} y2={sy(r[3])} stroke={c} strokeWidth={1} />
            <rect x={x - Math.max(bw * 0.35, 0.5)} y={Math.min(sy(r[1]), sy(r[4]))} width={Math.max(bw * 0.7, 1)} height={Math.max(Math.abs(sy(r[1]) - sy(r[4])), 1)} fill={c} />
          </g>
        );
      })}
      <text x={0} y={H - 4} fontSize={10} fill="var(--color-fg-faint)">
        {dt(rows[0][0])}
      </text>
      <text x={W - 60} y={H - 4} fontSize={10} fill="var(--color-fg-faint)" textAnchor="end">
        {dt(rows[rows.length - 1][0])}
      </text>
    </svg>
  );
}
