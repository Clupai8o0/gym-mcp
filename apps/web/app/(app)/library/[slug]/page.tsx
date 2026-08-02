import { cache, Suspense } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { IllustrationImage } from "@/components/library";
import { Badge, Button, Card, LocalTime, Skeleton } from "@/components/ui";
import { FadeIn } from "@/components/motion/FadeIn";
import { getExerciseBySlug, listPrsForExercise } from "@/lib/api";
import { formatPrValue, prTypeLabel, titleCase } from "@/lib/format";
import type { ExerciseDetail } from "@/lib/types";
import styles from "./page.module.css";

// One fetch shared by generateMetadata + the page (React per-request dedupe).
const loadExercise = cache((slug: string) => getExerciseBySlug(slug));

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const exercise = await loadExercise(slug);
  if (!exercise) return { title: "Exercise not found" };
  return {
    title: exercise.name,
    description: `How to perform ${exercise.name} — targets, equipment, and step-by-step instructions.`,
  };
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.metaRow}>
      <dt className={styles.metaLabel}>{label}</dt>
      <dd className={styles.metaValue}>{children}</dd>
    </div>
  );
}

/** Streams in after the hero — the PRs are below the fold and must not gate the LCP illustration. */
async function PrRecords({ exerciseId }: { exerciseId: string }) {
  const prs = await listPrsForExercise(exerciseId);
  if (prs.items.length === 0) {
    return (
      <p className={styles.empty}>
        No personal records yet — log a set for this exercise to start tracking.
      </p>
    );
  }
  return (
    <div className={styles.prGrid}>
      {prs.items.map((pr) => (
        <Card key={pr.id} className={styles.prCard}>
          <p className={styles.prLabel}>{prTypeLabel(pr.pr_type)}</p>
          <p className={`${styles.prValue} tnum`}>{formatPrValue(pr.value, pr.unit)}</p>
          <LocalTime iso={pr.achieved_at} className={styles.prDate} />
        </Card>
      ))}
    </div>
  );
}

function PrRecordsFallback() {
  return (
    <div className={styles.prGrid} aria-hidden>
      <Skeleton height="6rem" />
      <Skeleton height="6rem" />
    </div>
  );
}

export default async function ExerciseDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const exercise: ExerciseDetail | null = await loadExercise(slug);
  if (!exercise) notFound();

  const attributes = [
    exercise.category && { label: "Category", value: titleCase(exercise.category) },
    exercise.level && { label: "Level", value: titleCase(exercise.level) },
    exercise.mechanic && { label: "Mechanic", value: titleCase(exercise.mechanic) },
    exercise.force && { label: "Force", value: titleCase(exercise.force) },
    exercise.equipment && { label: "Equipment", value: titleCase(exercise.equipment) },
  ].filter(Boolean) as { label: string; value: string }[];

  return (
    <div className={styles.page}>
      <Link href="/library" className={styles.back}>
        ← Library
      </Link>

      <div className={styles.layout}>
        <div className={styles.media}>
          <IllustrationImage
            url={exercise.illustration_url}
            urlLight={exercise.illustration_url_light}
            status={exercise.illustration_status}
            name={exercise.name}
            shareName={`exercise-illustration-${exercise.slug}`}
            size="detail"
            priority
          />
        </div>

        <div className={styles.content}>
          <header className={styles.header}>
            {exercise.category && <p className="eyebrow">{titleCase(exercise.category)}</p>}
            <h1 className={styles.title}>{exercise.name}</h1>
            <div className={styles.tags}>
              {exercise.primary_muscles.map((muscle) => (
                <Badge key={muscle} tone="muscle">
                  {titleCase(muscle)}
                </Badge>
              ))}
              {exercise.secondary_muscles.map((muscle) => (
                <Badge key={muscle}>{titleCase(muscle)}</Badge>
              ))}
              {exercise.is_custom && <Badge tone="custom">Custom</Badge>}
            </div>
          </header>

          <div className={styles.actions}>
            <Link href={`/log?exercise=${exercise.slug}`}>
              <Button variant="primary">Log this exercise</Button>
            </Link>
          </div>

          {attributes.length > 0 && (
            <dl className={styles.meta}>
              {attributes.map((attribute) => (
                <MetaRow key={attribute.label} label={attribute.label}>
                  {attribute.value}
                </MetaRow>
              ))}
            </dl>
          )}
        </div>
      </div>

      <div className={styles.detailBody}>
        <section className={styles.section} aria-labelledby="how-to">
          <h2 id="how-to" className={styles.sectionTitle}>
            How to perform
          </h2>
          {exercise.instructions.length > 0 ? (
            <ol className={styles.steps}>
              {exercise.instructions.map((step, index) => (
                <FadeIn as="li" key={index} delay={index * 24} className={styles.step}>
                  <span className={styles.stepNumber} aria-hidden>
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </FadeIn>
              ))}
            </ol>
          ) : (
            <p className={styles.empty}>No instructions recorded for this exercise yet.</p>
          )}
        </section>

        <section className={styles.section} aria-labelledby="prs">
          <h2 id="prs" className={styles.sectionTitle}>
            Your records
          </h2>
          <Suspense fallback={<PrRecordsFallback />}>
            <PrRecords exerciseId={exercise.id} />
          </Suspense>
        </section>
      </div>
    </div>
  );
}
