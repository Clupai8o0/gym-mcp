import type { Metadata } from "next";

import { DashboardTabs, SkillsBoard } from "@/components/dashboard";
import { getSkillsOverview } from "@/lib/api";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Skills",
  description: "Track your calisthenics skill progression.",
};

export default async function SkillsPage() {
  const overview = await getSkillsOverview();
  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <p className="eyebrow">Progress</p>
        <h1 className={styles.title}>Skills</h1>
        <p className={styles.lede}>
          The calisthenics skill tree. Tap any skill to set your current stage and how far through
          it you are — your progress rings fill in.
        </p>
      </header>

      <DashboardTabs />

      <SkillsBoard skills={overview.items} />
    </div>
  );
}
