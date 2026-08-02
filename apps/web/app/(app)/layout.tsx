import { cookies } from "next/headers";

import { AppShell } from "@/components/app/AppShell";
import { SessionBar } from "@/components/app/SessionBar";
import { getActiveSession } from "@/lib/api";
import { parked, requireUser } from "@/lib/auth";
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
 *
 * The two reads it needs have no data dependency on each other, so they go out together — but
 * the user is resolved *first*, because on an expired cookie both fail and only one of them
 * knows how to redirect. See `lib/auth.parked`.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // The lifecycle flag from Phase 11A — `ended_at IS NULL`, never "is performed_at today?".
  // React-`cache`d, so the page below reuses this fetch rather than repeating it.
  const activeRead = parked(getActiveSession());
  // Read server-side so the rail is already the right width on the first paint (lib/rail).
  const railRead = cookies();

  await requireUser();

  const { session: active, set_count: setCount } = await activeRead;
  const railCollapsed = (await railRead).get(RAIL_COOKIE)?.value === RAIL_COLLAPSED;

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
