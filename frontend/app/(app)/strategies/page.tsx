"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Badge, EmptyState, ErrorState, Input, IssueList, LinkButton, LoadingBlock, PageHeader, Panel, Select, StatusBadge, Table, Value, Button } from "@/components/ui";
import { post } from "@/lib/api";
import { ago, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Page, Strategy } from "@/lib/types";

export default function StrategiesPage() {
  const router = useRouter();
  const [status, setStatus] = useState("active");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [importError, setImportError] = useState<unknown>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const path = `/strategies?status=${status}&limit=100${query ? `&q=${encodeURIComponent(query)}` : ""}`;
  const { data, error, loading, reload } = useApi<Page<Strategy>>(path);

  async function importFile(f: File) {
    setImportError(null);
    try {
      const document = JSON.parse(await f.text()) as Record<string, unknown>;
      const s = await post<Strategy>("/strategies/import", { document });
      router.push(`/strategies/${s.id}`);
    } catch (e) {
      setImportError(e instanceof SyntaxError ? new Error("The file is not valid JSON.") : e);
    }
  }

  return (
    <>
      <PageHeader
        title="Strategy Lab"
        subtitle="Versioned, rule-based strategies. Every saved change creates a new immutable version."
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              aria-label="Import strategy file"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importFile(f);
                e.target.value = "";
              }}
            />
            <Button onClick={() => fileRef.current?.click()}>Import JSON</Button>
            <LinkButton href="/strategies/new" variant="primary">
              New strategy
            </LinkButton>
          </>
        }
      />
      <IssueList error={importError} />
      <Panel
        pad={false}
        title={
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(q.trim());
            }}
          >
            <Input aria-label="Search strategies" placeholder="Search by name" className="h-7 w-52 text-xs" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select
              aria-label="Status filter"
              className="h-7 w-32 text-xs"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              options={[
                { value: "active", label: "Active" },
                { value: "archived", label: "Archived" },
                { value: "all", label: "All" },
              ]}
            />
          </form>
        }
      >
        {loading && !data ? (
          <div className="p-4">
            <LoadingBlock />
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        ) : data && data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState title={query || status !== "active" ? "No matching strategies" : "No strategies yet"} action={<LinkButton href="/strategies/new" variant="primary">Create your first strategy</LinkButton>}>
              Start from a template (EMA crossover, RSI reversion, breakout) or save a candidate from Discover.
            </EmptyState>
          </div>
        ) : data ? (
          <Table head={["Name", "Market", "Origin", "Versions", "Last backtest", "Status", "Updated"]}>
            {data.items.map((s) => {
              const d = s.current_version?.definition_json;
              return (
                <tr key={s.id}>
                  <td>
                    <Link href={`/strategies/${s.id}`} className="font-medium text-fg hover:text-accent">
                      {s.name}
                    </Link>
                  </td>
                  <td className="text-fg-muted">{d ? `${d.symbols.join(", ")} · ${d.timeframe} · ${d.direction.replace("_", "/")}` : "n/a"}</td>
                  <td>
                    <Badge>{s.origin}</Badge>
                  </td>
                  <td className="num">v{s.current_version?.version_number ?? "?"}</td>
                  <td>
                    {s.last_backtest ? (
                      <Link href={`/backtests/${s.last_backtest.id}`} className="hover:underline">
                        {s.last_backtest.status === "completed" ? <Value v={s.last_backtest.net_return} text={pct(s.last_backtest.net_return, 2, true)} /> : <StatusBadge status={s.last_backtest.status} />}
                      </Link>
                    ) : (
                      <span className="text-fg-faint">none</span>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="text-fg-muted">{ago(s.updated_at)}</td>
                </tr>
              );
            })}
          </Table>
        ) : null}
      </Panel>
    </>
  );
}
