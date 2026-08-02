import { FrequencyHeatmap } from "@/components/dashboard/FrequencyHeatmap";
import { VolumeChart } from "@/components/dashboard/VolumeChart";
import { SkillRing } from "@/components/dashboard/SkillRing";
import { Card } from "@/components/ui";
import { Reveal } from "./Reveal";
import { demoFrequency, demoRecords, demoSkills, demoVolume } from "./demoData";
import styles from "./DashboardPreview.module.css";

/**
 * The dashboard preview. Each surface gets its own heading and its own paragraph, so the section
 * is readable by a visitor skimming and by a crawler indexing.
 *
 * `VolumeChart` and `FrequencyHeatmap` are the app's own components, imported and rendered
 * unmodified against sample data. Nothing in `components/dashboard` is touched or forked to make
 * this work, which means the preview stays correct for free as those components evolve.
 */

/** Records and Skills are rebuilt from the same tokens. See the note in `demoData.ts` for why. */
function RecordsPanel() {
  return (
    <Card className={styles.panel}>
      <ul className={styles.records}>
        {demoRecords.map((record) => (
          <li key={record.name} className={styles.record}>
            <span className={styles.recordHead}>
              <span className={styles.recordName}>{record.name}</span>
              <span className={styles.recordLabel}>{record.label}</span>
            </span>
            <span className={styles.recordMeta}>
              <span className={`${styles.recordValue} tnum`}>{record.value}</span>
              <span className={styles.recordWhen}>{record.when}</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function SkillsPanel() {
  return (
    <Card className={styles.panel}>
      <ul className={styles.skills}>
        {demoSkills.map((skill) => (
          <li key={skill.name} className={styles.skill}>
            <SkillRing
              percent={skill.percent}
              currentStage={skill.stage}
              totalStages={skill.stages}
              size={72}
            />
            <span className={styles.skillBody}>
              <span className={styles.skillName}>{skill.name}</span>
              <span className={styles.skillStep}>{skill.step}</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const SURFACES = [
  {
    key: "volume",
    eyebrow: "Volume",
    title: "What you actually moved",
    body: "Sets, reps and tonnage totalled across whatever window you pick, then ranked by movement. The honest answer to “am I neglecting legs?” takes one glance instead of an afternoon in a spreadsheet. Bodyweight work counts too: sets drive the ranking, and tonnage is annotated only where a load exists.",
    node: <VolumeChart volume={demoVolume} unit="kg" />,
  },
  {
    key: "frequency",
    eyebrow: "Frequency",
    title: "Whether you actually showed up",
    body: "Sessions per week, Monday-anchored, with the empty weeks left in rather than quietly skipped. Consistency is the variable that moves everything else, and it is the one a streak counter is worst at telling the truth about. Tempo shows the shape of the block instead of a number you feel obliged to protect.",
    node: <FrequencyHeatmap frequency={demoFrequency} />,
  },
  {
    key: "records",
    eyebrow: "Records",
    title: "The moment it happened",
    body: "Every set is checked against your history as it lands: heaviest weight, most reps, longest hold. Records you entered by hand count as the bar to beat, not just previously logged sets. When one falls you hear about it at the rack, and the date it happened is kept for good.",
    node: <RecordsPanel />,
  },
  {
    key: "skills",
    eyebrow: "Skills",
    title: "The things that aren't a number",
    body: "Handstands, muscle-ups, front levers and pistol squats progress in stages rather than kilos, so they get their own board: which stage you are on, how far through it you are, and the next concrete thing to train. A secondary module, present if you want it and invisible if you don't.",
    node: <SkillsPanel />,
  },
] as const;

export function DashboardPreview() {
  return (
    <section id="dashboard" className={styles.section} aria-labelledby="dashboard-heading">
      <header className={styles.head}>
        <p className="eyebrow">The dashboard</p>
        <h2 id="dashboard-heading" className={styles.title}>
          Four questions, answered honestly.
        </h2>
        <p className={styles.lede}>
          Everything below is the running interface, not a screenshot. It is the same code the app
          renders after a workout, drawing a sample half-year of training so you can read it
          before you sign in.
        </p>
      </header>

      <div className={styles.grid}>
        {/*
          `Reveal`, not `FadeIn`. `FadeIn` fires on mount, and this section sits well below the
          fold, so its entrance would finish long before anyone scrolled to it: the cells would
          simply be there, out of step with every other band on the page. A view-progress
          timeline ties the entrance to arriving at the section instead.
        */}
        {SURFACES.map((surface, index) => (
          <Reveal key={surface.key} as="section" delay={index * 40} className={styles.cell}>
            <div className={styles.cellCopy}>
              <p className="eyebrow">{surface.eyebrow}</p>
              <h3 className={styles.cellTitle}>{surface.title}</h3>
              <p className={styles.cellBody}>{surface.body}</p>
            </div>
            <div className={styles.cellSurface}>{surface.node}</div>
          </Reveal>
        ))}
      </div>

      <p className={styles.disclosure}>
        Sample data. Your dashboard starts empty and fills in as you log.
      </p>
    </section>
  );
}
