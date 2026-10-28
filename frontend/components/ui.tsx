"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { useId } from "react";

import { errorIssues, errorMessage } from "@/lib/api";
import { NA, tone } from "@/lib/format";
import type { JobInfo } from "@/lib/types";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

/* ---------------------------------------------------------------- layout */
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-fg-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, actions, children, className, pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={cx("rounded-lg border border-line bg-panel shadow-[var(--shadow-panel)]", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h2 className="text-[13px] font-semibold text-fg">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

/* ---------------------------------------------------------------- buttons */
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md"; loading?: boolean };

const btnBase = "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
const btnVariant = {
  primary: "bg-accent text-[#06231a] hover:bg-accent-strong",
  secondary: "border border-line-strong bg-raised text-fg hover:border-fg-faint",
  ghost: "text-fg-muted hover:bg-raised hover:text-fg",
  danger: "border border-negative/40 bg-negative-soft text-negative hover:border-negative",
};
const btnSize = { sm: "h-7 px-2.5 text-xs", md: "h-8.5 px-3.5 text-[13px]" };

export function Button({ variant = "secondary", size = "md", loading, children, className, disabled, ...rest }: BtnProps) {
  return (
    <button type="button" {...rest} disabled={disabled || loading} className={cx(btnBase, btnVariant[variant], btnSize[size], className)}>
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export function LinkButton({ href, variant = "secondary", size = "md", children, className }: { href: string; variant?: BtnProps["variant"]; size?: "sm" | "md"; children: ReactNode; className?: string }) {
  return (
    <Link href={href} className={cx(btnBase, btnVariant[variant], btnSize[size], className)}>
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span aria-hidden className={cx("inline-block size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent", className)} />;
}

/* ---------------------------------------------------------------- form controls */
const inputCls = "h-8.5 w-full rounded-md border border-line-strong bg-panel-2 px-2.5 text-[13px] text-fg placeholder:text-fg-faint focus:border-accent focus:outline-none disabled:opacity-60";

export function Field({ label, hint, error, children, className }: { label: string; hint?: ReactNode; error?: string | null; children: (id: string) => ReactNode; className?: string }) {
  const id = useId();
  return (
    <div className={cx("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-xs font-medium text-fg-muted">
        {label}
      </label>
      {children(id)}
      {error ? <p className="text-xs text-negative">{error}</p> : hint ? <p className="text-xs text-fg-faint">{hint}</p> : null}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(inputCls, props.className)} />;
}

export function Select({ options, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  return (
    <select {...props} className={cx(inputCls, "pr-7", props.className)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(inputCls, "h-auto min-h-24 py-2 leading-relaxed", props.className)} />;
}

export function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-fg-muted">
      <input type="checkbox" className="size-3.5 accent-[var(--color-accent)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/* ---------------------------------------------------------------- data display */
export function Value({ v, text, className }: { v: unknown; text: string; className?: string }) {
  const t = tone(v);
  const arrow = t === 1 ? "▲" : t === -1 ? "▼" : "";
  return (
    <span className={cx("num", t === 1 && "text-accent", t === -1 && "text-negative", t === null && "text-fg-faint", className)}>
      {arrow && <span aria-hidden className="mr-0.5 text-[10px]">{arrow}</span>}
      {text}
    </span>
  );
}

export function Stat({ label, value, sub, title }: { label: string; value: ReactNode; sub?: ReactNode; title?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-panel-2 px-3 py-2.5" title={title}>
      <div className="truncate text-[11px] font-medium uppercase tracking-wide text-fg-faint">{label}</div>
      <div className="mt-1 truncate text-[17px] font-semibold">{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-fg-faint">{sub}</div>}
    </div>
  );
}

const badgeTone = {
  neutral: "border-line-strong text-fg-muted",
  positive: "border-accent/40 bg-accent-soft text-accent",
  negative: "border-negative/40 bg-negative-soft text-negative",
  warning: "border-warning/40 bg-warning-soft text-warning",
  info: "border-info/40 bg-info-soft text-info",
};

export function Badge({ tone: t = "neutral", children, title }: { tone?: keyof typeof badgeTone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 py-0.5 text-[11px] font-medium", badgeTone[t])}>
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, keyof typeof badgeTone> = {
  completed: "positive",
  validated: "positive",
  running: "info",
  queued: "neutral",
  created: "neutral",
  shortlisted: "info",
  awaiting_confirmation: "warning",
  confirmed: "positive",
  paused: "warning",
  stopped: "neutral",
  failed: "negative",
  rejected: "negative",
  cancelled: "neutral",
  active: "positive",
  archived: "neutral",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={STATUS_TONE[status] ?? "neutral"}>
      {(status === "running" || status === "queued") && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
      {status.replaceAll("_", " ")}
    </Badge>
  );
}

export function SyntheticBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return (
    <Badge tone="warning" title="Generated random data. Results say nothing about real markets.">
      Synthetic data
    </Badge>
  );
}

/* ---------------------------------------------------------------- states */
export function Notice({ tone: t = "info", title, children }: { tone?: "info" | "warning" | "negative" | "positive"; title?: string; children: ReactNode }) {
  const cls = {
    info: "border-info/30 bg-info-soft/60 text-info",
    warning: "border-warning/30 bg-warning-soft/60 text-warning",
    negative: "border-negative/30 bg-negative-soft/60 text-negative",
    positive: "border-accent/30 bg-accent-soft/60 text-accent",
  }[t];
  return (
    <div role={t === "negative" ? "alert" : "status"} className={cx("rounded-md border px-3 py-2.5 text-[13px]", cls)}>
      {title && <div className="mb-0.5 font-semibold">{title}</div>}
      <div className="text-fg/90">{children}</div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const issues = errorIssues(error);
  return (
    <Notice tone="negative" title="Could not load">
      <p>{errorMessage(error)}</p>
      {issues.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-xs">
          {issues.slice(0, 8).map((i, k) => (
            <li key={k}>
              {i.path && <code className="text-fg-muted">{i.path}: </code>}
              {i.message}
            </li>
          ))}
        </ul>
      )}
      {onRetry && (
        <Button size="sm" className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      )}
    </Notice>
  );
}

export function IssueList({ error }: { error: unknown }) {
  if (!error) return null;
  const issues = errorIssues(error);
  return (
    <Notice tone="negative" title={errorMessage(error)}>
      {issues.length > 0 && (
        <ul className="list-disc pl-4 text-xs">
          {issues.slice(0, 12).map((i, k) => (
            <li key={k}>
              {i.path && <code className="text-fg-muted">{i.path}: </code>}
              {i.message}
            </li>
          ))}
        </ul>
      )}
    </Notice>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line-strong px-6 py-10 text-center">
      <div className="text-sm font-semibold">{title}</div>
      {children && <div className="mt-1 max-w-md text-[13px] text-fg-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-md bg-raised", className)} />;
}

export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9" />
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- table */
export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-fg-faint">
            {head.map((h, i) => (
              <th key={i} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&>tr]:border-b [&>tr]:border-line/70 [&>tr:hover]:bg-raised/40 [&_td]:px-3 [&_td]:py-2">{children}</tbody>
      </table>
      {empty}
    </div>
  );
}

/* ---------------------------------------------------------------- tabs */
export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { value: T; label: string; disabled?: boolean }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          type="button"
          aria-selected={value === t.value}
          disabled={t.disabled}
          onClick={() => onChange(t.value)}
          className={cx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] font-medium transition-colors disabled:opacity-40",
            value === t.value ? "border-accent text-fg" : "border-transparent text-fg-muted hover:text-fg",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- jobs */
export function JobProgress({ job }: { job: JobInfo }) {
  if (!job) return null;
  const measured = job.progress_total && job.progress_total > 0;
  const pctDone = measured ? Math.round(((job.progress_current ?? 0) / (job.progress_total ?? 1)) * 100) : null;
  return (
    <div className="flex items-center gap-3 text-xs text-fg-muted">
      <StatusBadge status={job.status} />
      {measured && (
        <div className="flex min-w-40 items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-raised" role="progressbar" aria-valuenow={pctDone ?? 0} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full bg-accent transition-[width]" style={{ width: `${pctDone}%` }} />
          </div>
          <span className="num">
            {job.progress_current}/{job.progress_total}
          </span>
        </div>
      )}
      {job.cancel_requested && job.status === "running" && <span>Cancelling…</span>}
      {job.error_message && <span className="text-negative">{job.error_message}</span>}
    </div>
  );
}

export function KV({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,auto)_1fr] gap-x-4 gap-y-1.5 text-[13px]">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-fg-faint">{k}</dt>
          <dd className="min-w-0 truncate text-fg">{v ?? NA}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Hash({ value, len = 10 }: { value: string | null | undefined; len?: number }) {
  if (!value) return <span className="text-fg-faint">{NA}</span>;
  return (
    <code className="num text-xs text-fg-muted" title={value}>
      {value.slice(0, len)}
    </code>
  );
}
