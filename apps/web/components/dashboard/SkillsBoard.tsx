"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { EmptyState } from "@/components/ui";
import { Pressable } from "@/components/motion/Pressable";
import { Stagger } from "@/components/motion/Stagger";
import type { SkillOverview, SkillProgress } from "@/lib/types";
import { SkillEditor } from "./SkillEditor";
import { SkillRing } from "./SkillRing";
import styles from "./SkillsBoard.module.css";

/** A one-line status under each ring. */
function caption(skill: SkillOverview): string {
  if (skill.current_stage === 0 && skill.progress_percent === 0) return "Not started";
  return `Stage ${skill.current_stage} of ${skill.total_stages} · ${skill.progress_percent}%`;
}

/**
 * The Skills module (docs/07 §Skills): a grid of progress rings the user can tap to edit. Seeds
 * from the server overview, then applies each save into local state so the ring updates instantly.
 * The editor targets a skill by slug (not a snapshot), so re-opening always shows current values.
 */
export function SkillsBoard({ skills }: { skills: SkillOverview[] }) {
  const router = useRouter();
  const [items, setItems] = useState(skills);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const editing = items.find((item) => item.slug === editingSlug) ?? null;

  const onSaved = (slug: string, progress: SkillProgress) => {
    setItems((prev) =>
      prev.map((item) =>
        item.slug === slug
          ? {
              ...item,
              current_stage: progress.current_stage,
              progress_percent: progress.progress_percent,
              stage_name: progress.stage_name,
              notes: progress.notes,
              updated_at: progress.updated_at,
            }
          : item,
      ),
    );
    setOpen(false);
    // Home's "Top skill" highlight is rendered from this same data on another route, and the
    // client router holds that render for `staleTimes.dynamic` (next.config.ts). Invalidate so
    // navigating home doesn't show the progress this save just replaced.
    router.refresh();
  };

  if (items.length === 0) {
    return (
      <EmptyState
        title="No skills yet"
        description="The calisthenics skill tree will appear here once it's set up for your account."
      />
    );
  }

  return (
    <>
      <Stagger className={styles.grid} step={22} max={13}>
        {items.map((skill) => (
          <button
            key={skill.slug}
            type="button"
            className={styles.card}
            aria-haspopup="dialog"
            aria-expanded={open && editingSlug === skill.slug}
            aria-label={`Edit ${skill.name} — ${caption(skill)}`}
            onClick={() => {
              setEditingSlug(skill.slug);
              setOpen(true);
            }}
          >
            <Pressable className={styles.press}>
              <SkillRing
                percent={skill.progress_percent}
                currentStage={skill.current_stage}
                totalStages={skill.total_stages}
              />
              <span className={styles.name}>{skill.name}</span>
              <span className={styles.meta}>{caption(skill)}</span>
            </Pressable>
          </button>
        ))}
      </Stagger>

      <SkillEditor skill={editing} open={open} onClose={() => setOpen(false)} onSaved={onSaved} />
    </>
  );
}
