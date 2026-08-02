/**
 * Landing-page copy, kept in one place so the visible FAQ and the FAQPage JSON-LD are generated
 * from the same source and cannot drift apart. Google treats structured data that disagrees with
 * the visible page as a spam signal, so this is a correctness concern, not just tidiness.
 *
 * Every claim here is checked against the codebase. Where a capability is narrower than the
 * obvious marketing phrasing would imply, the narrower version is what ships: offline covers set
 * writes only, and there is no billing to describe yet.
 */

export interface Faq {
  q: string;
  a: string;
}

export const FAQS: Faq[] = [
  {
    q: "Do I have to build my own exercise list?",
    a: "No. Tempo ships with a general-gym catalog of over 800 movements, each with a minimal line-art illustration, filterable by muscle, equipment and difficulty. You can add your own exercises on top, and they are marked as custom so you can tell them apart.",
  },
  {
    q: "Does it work without signal in the gym?",
    a: "Logging does. When a set cannot reach the server it is written to your device and flushed automatically as soon as you reconnect, so a dead spot never costs you a workout. Browsing the library and loading the dashboard still need a connection. Tempo also installs as an app on iOS and Android.",
  },
  {
    q: "Kilograms or pounds?",
    a: "Either. Pick a unit in settings and every weight, tonnage total and personal record is converted for you. Weights are stored in kilograms underneath, so switching units never rounds your history away.",
  },
  {
    q: "How does Tempo know something is a personal record?",
    a: "Every set is compared against your history the moment you log it, across heaviest weight, most reps and longest hold. Records you typed in yourself count as the bar to beat, not just sets you logged in the app, so your first week in Tempo does not hand you a dozen fake bests.",
  },
  {
    q: "Can I use it from Claude or ChatGPT?",
    a: "Yes. Tempo runs an MCP server alongside its API, so a chat client can read your training and log sets over an OAuth connection you approve and can revoke at any time. You can ask what you benched last Tuesday, or log a set, without opening the app.",
  },
  {
    q: "What about calisthenics skills?",
    a: "Skills like handstands, muscle-ups and front levers progress in stages rather than kilos, so they get a separate board tracking which stage you are on and the next concrete step to train. It is a secondary module: use it or ignore it, and the rest of the app is unaffected.",
  },
  {
    q: "Who can see my training?",
    a: "Only you. Tempo is personal-first, there is no feed and no social layer, and sign-in is delegated to Google so Tempo never handles a password. Sharing is something you opt into later, not a default.",
  },
];

export interface Stat {
  label: string;
  value: string;
}

export const STATS: Stat[] = [
  { label: "Catalog", value: "800+ exercises" },
  { label: "Set entry", value: "Weight, reps, holds" },
  { label: "Dashboard", value: "Volume, records, frequency" },
  { label: "Chat", value: "MCP over OAuth" },
];

export interface Feature {
  id: string;
  eyebrow: string;
  title: string;
  /** Two paragraphs. The first says what it is, the second says why it is built that way. */
  body: [string, string];
  points: string[];
}

export const FEATURES: Feature[] = [
  {
    id: "library",
    eyebrow: "The library",
    title: "Every movement, illustrated.",
    body: [
      "Over eight hundred exercises drawn in one monochrome line-art style, so a barbell row and a cable fly look like they belong to the same system. Filter by muscle worked, by the equipment actually in front of you, or by difficulty when you are starting out.",
      "The catalog is drawn from free-exercise-db, which is public domain, so there is no licensing asterisk on what you can do with your own training log. Illustrations are generated ahead of time and served as immutable assets, which is why the library scrolls without the usual flicker of half-loaded thumbnails.",
    ],
    points: [
      "Search by name, muscle, equipment or level",
      "Add custom movements the catalog does not cover",
      "Every exercise links straight into logging",
    ],
  },
  {
    id: "logging",
    eyebrow: "Logging",
    title: "Fast enough to use between sets.",
    body: [
      "Weight, reps and holds go in from a number pad built for one thumb and a chalky hand, not a desktop form squeezed onto a phone. Start a session, add exercises as you go, and the rest timer picks up from the set you just finished.",
      "Records are checked as each set lands rather than in a nightly job, so the app tells you at the rack instead of a week later. If the gym has no signal the set is stored on your device and syncs the moment you walk back out, which means the log never depends on the building's wifi.",
    ],
    points: [
      "One-handed number pad, tuned for mid-workout",
      "Rest timer carries over between sets",
      "Sets queue offline and sync on reconnect",
    ],
  },
];

export interface Step {
  n: string;
  title: string;
  body: string;
}

export const STEPS: Step[] = [
  {
    n: "01",
    title: "Sign in with Google",
    body: "No password to invent and none for Tempo to lose. You are logging inside a minute.",
  },
  {
    n: "02",
    title: "Log your first session",
    body: "Pick movements from the catalog, enter sets as you do them, and finish when you are done.",
  },
  {
    n: "03",
    title: "Watch the record fill in",
    body: "Volume, frequency and records build from the sets you log. Nothing to configure first.",
  },
];
