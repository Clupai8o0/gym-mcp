import type { Metadata } from "next";

import { SkillsBoard } from "@/components/dashboard";
import { getSkillsOverview } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import styles from "../progress.module.css";

export const metadata: Metadata = {
  title: "Skills",
  description: "Track your calisthenics skill progression.",
};

/** The calisthenics skill tree — the secondary module, now a sibling of the other progress views. */
export default async function SkillsPage() {
  const [, overview] = await Promise.all([requireUser("/progress/skills"), getSkillsOverview()]);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.titleBlock}>
          <p className="eyebrow">Progress</p>
          <h1 className={styles.title}>Skills</h1>
          <p className={styles.lede}>
            Tap any skill to set your current stage and how far through it you are — your progress
            rings fill in.
          </p>
        </div>
      </header>

      <SkillsBoard skills={overview.items} />
    </div>
  );
}
