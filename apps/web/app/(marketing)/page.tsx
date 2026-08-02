import type { Metadata } from "next";
import Link from "next/link";

import { Logo } from "@/components/app/Logo";
import { DashboardPreview } from "@/components/marketing/DashboardPreview";
import { Reveal } from "@/components/marketing/Reveal";
import { RidgeField } from "@/components/marketing/RidgeField";
import { FAQS, FEATURES, STATS, STEPS } from "@/components/marketing/content";
import { Button, Card } from "@/components/ui";
import { loginUrl } from "@/lib/auth";
import { BASE_URL } from "@/lib/env";
import styles from "./page.module.css";

const TITLE = "Tempo: a workout log you can actually read";
const DESCRIPTION =
  "An illustrated library of 800+ exercises, set logging fast enough to use between sets, and a dashboard that turns six months of training into one honest picture. Connects to Claude over MCP.";

export const metadata: Metadata = {
  // `default`, not a plain string: the root layout's template appends " · Tempo", which would
  // otherwise stutter against a title that already ends in the product name.
  title: { absolute: TITLE },
  description: DESCRIPTION,
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: BASE_URL,
    siteName: "Tempo",
    title: TITLE,
    description: DESCRIPTION,
  },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
};

/**
 * Structured data for the landing page.
 *
 * The FAQ entries come from the same array the visible section renders, because structured data
 * that disagrees with the page it describes is treated as a spam signal rather than ignored.
 *
 * No `offers` node: Tempo has no billing, and asserting a price it does not charge would be a
 * false claim in a field search engines surface directly.
 */
function StructuredData() {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        name: "Tempo",
        applicationCategory: "HealthApplication",
        operatingSystem: "Web, iOS, Android",
        url: BASE_URL,
        description: DESCRIPTION,
        featureList: [
          "Illustrated exercise library of 800+ movements",
          "Fast one-handed set logging with rest timer",
          "Automatic personal-record detection",
          "Training volume, frequency and records dashboard",
          "Calisthenics skill progression",
          "MCP server for chat clients over OAuth",
        ],
      },
      {
        "@type": "FAQPage",
        mainEntity: FAQS.map((faq) => ({
          "@type": "Question",
          name: faq.q,
          acceptedAnswer: { "@type": "Answer", text: faq.a },
        })),
      },
    ],
  };
  return (
    <script
      type="application/ld+json"
      // Escaping `<` closes off the one way a string in this payload could break out of the
      // script element. Everything here is authored copy, but the guard costs nothing.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph).replace(/</g, "\\u003c") }}
    />
  );
}

function Topbar() {
  return (
    <header className={styles.topbar}>
      <span className={styles.logo}>
        <Logo />
        Tempo
      </span>
      <nav className={styles.nav} aria-label="Sections">
        <Link href="#library" className={styles.navLink}>
          Library
        </Link>
        <Link href="#logging" className={styles.navLink}>
          Logging
        </Link>
        <Link href="#dashboard" className={styles.navLink}>
          Dashboard
        </Link>
        <Link href="#chat" className={styles.navLink}>
          Chat
        </Link>
        <Link href={loginUrl()}>
          <Button variant="outline" size="sm">
            Sign in
          </Button>
        </Link>
      </nav>
    </header>
  );
}

function Hero() {
  return (
    <section className={styles.hero}>
      <div className={styles.field}>
        <RidgeField />
      </div>

      <div className={styles.heroCopy}>
        <p className={`eyebrow ${styles.heroEyebrow}`}>Personal-first training log</p>
        <h1 className={styles.heroTitle}>Six months, one honest picture.</h1>
        <p className={styles.heroLede}>
          Every set you log becomes a mark on the record: volume by movement, sessions by week,
          and the exact day each personal best landed. No streak guilt, no vanity score. Just what
          you actually did, kept somewhere you can read it.
        </p>
        {/* No caption under the CTAs. The backdrop is abstract, unlabelled and aria-hidden, so
            it asserts nothing that would need a "sample data" disclosure; the dashboard preview
            carries its own, because that section does make concrete numeric claims. */}
        <div className={styles.heroCta}>
          <Link href={loginUrl()}>
            <Button variant="primary">Start training</Button>
          </Link>
          <Link href="#dashboard">
            <Button variant="outline">See the dashboard</Button>
          </Link>
        </div>
      </div>
    </section>
  );
}

function Stats() {
  return (
    <Reveal as="section" className={styles.stats} aria-label="At a glance">
      <dl className={styles.statsList}>
        {STATS.map((stat) => (
          <div key={stat.label} className={styles.stat}>
            <dt className={`eyebrow ${styles.statLabel}`}>{stat.label}</dt>
            <dd className={styles.statValue}>{stat.value}</dd>
          </div>
        ))}
      </dl>
    </Reveal>
  );
}

function Features() {
  return (
    <>
      {FEATURES.map((feature) => (
        <Reveal
          as="section"
          key={feature.id}
          id={feature.id}
          className={styles.feature}
          aria-labelledby={`${feature.id}-heading`}
        >
          <div className={styles.featureCopy}>
            <p className="eyebrow">{feature.eyebrow}</p>
            <h2 id={`${feature.id}-heading`} className={styles.featureTitle}>
              {feature.title}
            </h2>
            {feature.body.map((paragraph) => (
              <p key={paragraph.slice(0, 24)} className={styles.featureBody}>
                {paragraph}
              </p>
            ))}
          </div>
          {/* No per-item stagger here: the whole band already reveals as one unit on scroll,
              and staggering inside something that is itself entering reads as fussy. */}
          <ul className={styles.featurePoints}>
            {feature.points.map((point) => (
              <li key={point} className={styles.featurePoint}>
                {point}
              </li>
            ))}
          </ul>
        </Reveal>
      ))}
    </>
  );
}

function Steps() {
  return (
    <Reveal as="section" className={styles.steps} aria-labelledby="steps-heading">
      <div className={styles.stepsHead}>
        <p className="eyebrow">Getting started</p>
        <h2 id="steps-heading" className={styles.sectionTitle}>
          Three steps, no setup.
        </h2>
      </div>
      <ol className={styles.stepsList}>
        {STEPS.map((step) => (
          <li key={step.n} className={styles.step}>
            <span className={`eyebrow ${styles.stepNumber}`}>{step.n}</span>
            <h3 className={styles.stepTitle}>{step.title}</h3>
            <p className={styles.stepBody}>{step.body}</p>
          </li>
        ))}
      </ol>
    </Reveal>
  );
}

function Chat() {
  return (
    <Reveal as="section" id="chat" className={styles.chat} aria-labelledby="chat-heading">
      <div className={styles.chatCopy}>
        <p className="eyebrow">Connected</p>
        <h2 id="chat-heading" className={styles.sectionTitle}>
          Ask your training in plain language.
        </h2>
        <p className={styles.featureBody}>
          Tempo runs an MCP server next to its API, so a chat client like Claude can read your
          training and log sets through a connection you approve yourself. The same functions
          serve both, which means the answer you get in chat is the answer the app would give.
        </p>
        <p className={styles.featureBody}>
          Access is scoped and revocable. You grant it from settings, you can see exactly what is
          connected, and you can cut it off at any time without touching your data.
        </p>
      </div>

      <Card className={styles.chatDemo}>
        <p className={styles.chatTurn}>
          <span className={`eyebrow ${styles.chatWho}`}>You</span>
          What did I bench last Tuesday, and was it a record?
        </p>
        <p className={`${styles.chatTurn} ${styles.chatTurnReply}`}>
          <span className={`eyebrow ${styles.chatWho}`}>Claude</span>
          Four sets of Barbell Bench Press, topping out at 82.5 kg for 8. That top set was a
          personal record, up from 80 kg three weeks earlier.
        </p>
      </Card>
    </Reveal>
  );
}

function Faq() {
  return (
    <Reveal as="section" id="faq" className={styles.faq} aria-labelledby="faq-heading">
      <div className={styles.faqHead}>
        <p className="eyebrow">Questions</p>
        <h2 id="faq-heading" className={styles.sectionTitle}>
          The things worth asking first.
        </h2>
      </div>
      <dl className={styles.faqList}>
        {FAQS.map((faq) => (
          <div key={faq.q} className={styles.faqItem}>
            <dt className={styles.faqQuestion}>{faq.q}</dt>
            <dd className={styles.faqAnswer}>{faq.a}</dd>
          </div>
        ))}
      </dl>
    </Reveal>
  );
}

function FinalCta() {
  return (
    <Reveal as="section" className={styles.finalCta} aria-labelledby="cta-heading">
      <h2 id="cta-heading" className={styles.finalCtaTitle}>
        Start the record today.
      </h2>
      <p className={styles.finalCtaBody}>
        Six months from now the only thing that matters is whether you kept one.
      </p>
      <Link href={loginUrl()}>
        <Button variant="primary">Sign in with Google</Button>
      </Link>
    </Reveal>
  );
}

function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerBrand}>
        <span className={styles.logo}>
          <Logo />
          Tempo
        </span>
        <span className={styles.footerMuted}>Personal-first, share-ready.</span>
      </div>
      <nav className={styles.footerNav} aria-label="Footer">
        <Link href="#library" className={styles.navLink}>
          Library
        </Link>
        <Link href="#logging" className={styles.navLink}>
          Logging
        </Link>
        <Link href="#dashboard" className={styles.navLink}>
          Dashboard
        </Link>
        <Link href="#faq" className={styles.navLink}>
          FAQ
        </Link>
      </nav>
      <p className={styles.footerMuted}>
        Exercise data from free-exercise-db, released into the public domain.
      </p>
    </footer>
  );
}

export default function MarketingPage() {
  return (
    <div className={styles.root}>
      <StructuredData />
      {/* Keyboard users land here first and can jump the five nav stops in one press. */}
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>
      <Topbar />
      <main id="main">
        <Hero />
        <Stats />
        <Features />
        <DashboardPreview />
        <Steps />
        <Chat />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
