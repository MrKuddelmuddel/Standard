"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { StrategyEditor } from "@/components/strategy-editor";
import { cx, PageHeader } from "@/components/ui";
import { post } from "@/lib/api";
import { emptyDefinition, TEMPLATES } from "@/lib/strategy";
import type { Strategy, StrategyDefinition } from "@/lib/types";

export default function NewStrategyPage() {
  const router = useRouter();
  const [template, setTemplate] = useState<string>(TEMPLATES[0].id);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const initial = template === "blank" ? emptyDefinition() : (TEMPLATES.find((t) => t.id === template)?.build() ?? emptyDefinition());

  async function save(d: StrategyDefinition) {
    setSaving(true);
    setError(null);
    try {
      const s = await post<Strategy>("/strategies", { name: d.name, description: d.description ?? "", definition: d });
      router.push(`/strategies/${s.id}?tab=backtest`);
    } catch (e) {
      setError(e);
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="New strategy" subtitle="Pick a starting point, adjust the rules, validate and save. Saving creates version 1." />
      <div className="mb-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-4" role="radiogroup" aria-label="Template">
        {[...TEMPLATES, { id: "blank", name: "Blank", description: "Start from scratch with no indicators or rules." }].map((t) => (
          <button
            key={t.id}
            type="button"
            role="radio"
            aria-checked={template === t.id}
            onClick={() => setTemplate(t.id)}
            className={cx("rounded-lg border px-3 py-2.5 text-left transition-colors", template === t.id ? "border-accent bg-accent-soft/40" : "border-line bg-panel hover:border-line-strong")}
          >
            <div className="text-[13px] font-semibold">{t.name}</div>
            <div className="mt-0.5 text-xs text-fg-muted">{t.description}</div>
          </button>
        ))}
      </div>
      <StrategyEditor key={template} initial={initial} onSave={(d) => void save(d)} saving={saving} saveError={error} saveLabel="Save strategy" />
    </>
  );
}
