// Consistent number, currency, percent and time formatting. Times are shown in UTC to match the data.

const nf = (min: number, max: number) => new Intl.NumberFormat("en-US", { minimumFractionDigits: min, maximumFractionDigits: max });
const n0 = nf(0, 0);
const n2 = nf(2, 2);

export const NA = "n/a";

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function num(v: unknown, digits = 2): string {
  return isNum(v) ? nf(digits, digits).format(v) : NA;
}

export function int(v: unknown): string {
  return isNum(v) ? n0.format(v) : NA;
}

export function money(v: unknown, signed = false): string {
  if (!isNum(v)) return NA;
  const s = n2.format(Math.abs(v));
  if (signed) return `${v > 0 ? "+" : v < 0 ? "−" : ""}$${s}`;
  return `${v < 0 ? "−" : ""}$${s}`;
}

export function pct(v: unknown, digits = 2, signed = false): string {
  if (!isNum(v)) return NA;
  const s = nf(digits, digits).format(Math.abs(v * 100));
  const sign = v > 0 ? (signed ? "+" : "") : v < 0 ? "−" : "";
  return `${sign}${s}%`;
}

export function price(v: unknown): string {
  if (!isNum(v)) return NA;
  if (Math.abs(v) >= 1000) return nf(2, 2).format(v);
  if (Math.abs(v) >= 1) return nf(2, 4).format(v);
  return nf(4, 6).format(v);
}

export function qty(v: unknown): string {
  return isNum(v) ? nf(0, 6).format(v) : NA;
}

function toDate(v: string | number | Date): Date {
  return v instanceof Date ? v : new Date(v);
}

export function dt(v: string | number | Date | null | undefined): string {
  if (v === null || v === undefined || v === "") return NA;
  const d = toDate(v);
  if (Number.isNaN(d.getTime())) return NA;
  return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

export function date(v: string | number | Date | null | undefined): string {
  if (v === null || v === undefined || v === "") return NA;
  const d = toDate(v);
  return Number.isNaN(d.getTime()) ? NA : d.toISOString().slice(0, 10);
}

export function ago(v: string | number | Date | null | undefined): string {
  if (!v) return NA;
  const s = Math.round((Date.now() - toDate(v).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

/** -1, 0 or 1 for coloring; null when the value is missing. */
export function tone(v: unknown): -1 | 0 | 1 | null {
  if (!isNum(v)) return null;
  return v > 0 ? 1 : v < 0 ? -1 : 0;
}

export const formatJson = (v: unknown) => JSON.stringify(v, null, 2);
