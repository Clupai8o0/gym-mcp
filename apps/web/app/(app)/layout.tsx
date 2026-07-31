import { OfflineIndicator } from "@/components/app/OfflineIndicator";
import { SessionBar } from "@/components/app/SessionBar";
import { TabBar } from "@/components/app/TabBar";
import { getActiveSession, getSession } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import styles from "./layout.module.css";

/**
 * Authenticated shell (docs/07, rebuilt mobile-first in Phase 11B). Resolves the session
 * server-side and redirects to Google login when absent — app chrome is never rendered for
 * signed-out users.
 *
 * There is no top bar. Navigation lives at the bottom of the screen inside the thumb arc (a
 * left rail from 768px up), each screen carries its own title row that scrolls away with the
 * content, and the docked `SessionBar` keeps a live workout one tap away from every route.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  await requireUser();

  // The lifecycle flag from Phase 11A — `ended_at IS NULL`, never "is performed_at today?".
  const active = await getActiveSession();
  // Both reads are React-`cache`d, so `/log/[id]` reuses this fetch rather than repeating it.
  const detail = active ? await getSession(active.id) : null;
  const setCount = detail
    ? detail.exercises.reduce((total, group) => total + group.sets.length, 0)
    : 0;

  return (
    <div className={styles.shell} data-session={active ? "true" : undefined}>
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>

      <TabBar sessionActive={Boolean(active)} />

      <main id="main" tabIndex={-1} className={styles.main}>
        {children}
      </main>

      <div className={styles.dock}>
        <div className={styles.dockChip}>
          <OfflineIndicator />
        </div>
        {active && (
          <SessionBar
            sessionId={active.id}
            title={active.title}
            setCount={setCount}
            startedAt={active.performed_at}
          />
        )}
      </div>
    </div>
  );
}
