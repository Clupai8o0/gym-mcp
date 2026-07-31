import { cookies } from "next/headers";

import { AppShell } from "@/components/app/AppShell";
import { SessionBar } from "@/components/app/SessionBar";
import { getActiveSession, getSession } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { RAIL_COLLAPSED, RAIL_COOKIE } from "@/lib/rail";

/**
 * Authenticated shell (docs/07, rebuilt mobile-first in Phase 11B). Resolves the session
 * server-side and redirects to Google login when absent — app chrome is never rendered for
 * signed-out users.
 *
 * There is no top bar. Navigation lives at the bottom of the screen inside the thumb arc (a
 * collapsible left rail from 768px up), each screen carries its own title row that scrolls away
 * with the content, and the docked `SessionBar` keeps a live workout one tap away from every
 * route. This half does the data work; `AppShell` owns the interactive chrome state.
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

  // Read server-side so the rail is already the right width on the first paint (lib/rail).
  const railCollapsed = (await cookies()).get(RAIL_COOKIE)?.value === RAIL_COLLAPSED;

  return (
    <AppShell
      sessionActive={Boolean(active)}
      railCollapsed={railCollapsed}
      sessionBar={
        active ? (
          <SessionBar
            sessionId={active.id}
            title={active.title}
            setCount={setCount}
            startedAt={active.performed_at}
          />
        ) : null
      }
    >
      {children}
    </AppShell>
  );
}
