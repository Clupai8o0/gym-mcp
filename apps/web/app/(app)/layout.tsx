import { AppHeader } from "@/components/app/AppHeader";
import { requireUser } from "@/lib/auth";
import styles from "./layout.module.css";

/**
 * Authenticated shell (docs/07). Resolves the session server-side and redirects to Google login
 * when absent — app chrome is never rendered for signed-out users. Everything below the header
 * animates during route transitions; the header stays anchored (globals.css / AppHeader).
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const me = await requireUser();
  return (
    <div className={styles.shell}>
      <AppHeader me={me} />
      <main className={styles.main}>{children}</main>
    </div>
  );
}
