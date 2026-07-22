import Link from "next/link";

import { Button, Card } from "@/components/ui";
import { FadeIn } from "@/components/motion/FadeIn";
import { loginUrl } from "@/lib/auth";
import styles from "./page.module.css";

const FEATURES = [
  {
    eyebrow: "Library",
    title: "Every movement, illustrated",
    body: "800+ exercises with minimal line-art illustrations, searchable by muscle, equipment, and level.",
  },
  {
    eyebrow: "Logging",
    title: "Fast, one-handed set entry",
    body: "Log weight, reps, and holds mid-workout. Personal records surface the moment you hit them.",
  },
  {
    eyebrow: "Anywhere",
    title: "Read and update from chat",
    body: "Connect Tempo to Claude over a secure link and manage your training in plain language.",
  },
];

export default function MarketingPage() {
  return (
    <div className={styles.root}>
      <header className={styles.topbar}>
        <span className={styles.logo}>
          <span className={styles.mark} aria-hidden />
          Tempo
        </span>
        <Link href={loginUrl("/library")}>
          <Button variant="outline" size="sm">
            Sign in
          </Button>
        </Link>
      </header>

      <main>
        <section className={styles.hero}>
          <FadeIn>
            <p className="eyebrow">Personal-first workout tracking</p>
          </FadeIn>
          <FadeIn delay={40}>
            <h1 className={styles.title}>Train with intention.</h1>
          </FadeIn>
          <FadeIn delay={80}>
            <p className={styles.lede}>
              An illustrated exercise library, fast workout logging, and a progress dashboard — one
              calm, precise app that&apos;s yours, and ready to share when you are.
            </p>
          </FadeIn>
          <FadeIn delay={120}>
            <div className={styles.cta}>
              <Link href={loginUrl("/library")}>
                <Button variant="primary">Sign in with Google</Button>
              </Link>
              <Link href="/library">
                <Button variant="outline">Browse the library</Button>
              </Link>
            </div>
          </FadeIn>
        </section>

        <section className={styles.features} aria-label="What Tempo does">
          {FEATURES.map((feature, index) => (
            <FadeIn key={feature.eyebrow} delay={index * 60}>
              <Card className={styles.feature}>
                <p className="eyebrow">{feature.eyebrow}</p>
                <h2 className={styles.featureTitle}>{feature.title}</h2>
                <p className={styles.featureBody}>{feature.body}</p>
              </Card>
            </FadeIn>
          ))}
        </section>
      </main>

      <footer className={styles.footer}>
        <span>Tempo</span>
        <span className={styles.footerMuted}>Personal-first, share-ready.</span>
      </footer>
    </div>
  );
}
