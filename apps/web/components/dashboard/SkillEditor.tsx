"use client";

import { useState } from "react";
import dynamic from "next/dynamic";

import { Button, Input, Select } from "@/components/ui";
import { ClientApiError, NetworkError, updateSkillProgress } from "@/lib/client";
import type { SkillOverview, SkillProgress } from "@/lib/types";
import styles from "./SkillEditor.module.css";

// The editor Sheet opens only on a tap, so defer `motion` off the Dashboard/Skills initial bundle.
const Sheet = dynamic(() => import("@/components/motion/Sheet").then((m) => m.Sheet), {
  ssr: false,
});

interface SkillFormProps {
  skill: SkillOverview;
  onClose: () => void;
  onSaved: (slug: string, progress: SkillProgress) => void;
}

/** Stage options 0…total ("Not started", then "Stage n"). */
function stageOptions(total: number): { value: string; label: string }[] {
  return Array.from({ length: total + 1 }, (_, stage) => ({
    value: String(stage),
    label: stage === 0 ? "Not started" : `Stage ${stage}`,
  }));
}

/** The controlled edit form — remounted per skill (via `key`) so its state seeds cleanly. */
function SkillForm({ skill, onClose, onSaved }: SkillFormProps) {
  const [stage, setStage] = useState(skill.current_stage);
  const [percent, setPercent] = useState(skill.progress_percent);
  const [stageName, setStageName] = useState(skill.stage_name ?? "");
  const [notes, setNotes] = useState(skill.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const progress = await updateSkillProgress(skill.slug, {
        current_stage: stage,
        progress_percent: percent,
        stage_name: stageName.trim() || null,
        notes: notes.trim() || null,
      });
      onSaved(skill.slug, progress);
    } catch (caught) {
      if (caught instanceof NetworkError) {
        setError("You appear to be offline. Try again once you reconnect.");
      } else if (caught instanceof ClientApiError) {
        setError(caught.message);
      } else {
        throw caught;
      }
      setSaving(false);
    }
  };

  return (
    <div className={styles.form}>
      <header className={styles.header}>
        <p className="eyebrow">Edit skill</p>
        <h2 className={styles.title}>{skill.name}</h2>
      </header>

      <label className={styles.field}>
        <span className={styles.label}>Current stage</span>
        <Select
          options={stageOptions(skill.total_stages)}
          value={String(stage)}
          onChange={(event) => setStage(Number(event.target.value))}
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>
          Progress through stage
          <span className={`${styles.percent} tnum`}>{percent}%</span>
        </span>
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={percent}
          onChange={(event) => setPercent(Number(event.target.value))}
          className={styles.slider}
          aria-label="Progress percent"
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Stage name (optional)</span>
        <Input
          value={stageName}
          onChange={(event) => setStageName(event.target.value)}
          placeholder="e.g. Tuck planche"
          maxLength={100}
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Notes (optional)</span>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Cues, targets, what's next…"
          className={styles.textarea}
          rows={3}
        />
      </label>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <div className={styles.actions}>
        <Button variant="ghost" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button variant="primary" onClick={save} loading={saving}>
          Save progress
        </Button>
      </div>
    </div>
  );
}

export interface SkillEditorProps {
  skill: SkillOverview | null;
  open: boolean;
  onClose: () => void;
  onSaved: (slug: string, progress: SkillProgress) => void;
}

/**
 * The skill-progress editor in a right-side {@link Sheet}. The form mounts only while open (keyed
 * by slug), so every open re-seeds from current data and resets its own submit state. Writes go
 * through the same skills service the MCP `update_skill_progress` tool uses (Phase 5 contract).
 */
export function SkillEditor({ skill, open, onClose, onSaved }: SkillEditorProps) {
  return (
    <Sheet
      open={open}
      onClose={onClose}
      side="right"
      label={skill ? `Edit ${skill.name}` : "Edit skill"}
    >
      {open && skill && (
        <SkillForm key={skill.slug} skill={skill} onClose={onClose} onSaved={onSaved} />
      )}
    </Sheet>
  );
}
