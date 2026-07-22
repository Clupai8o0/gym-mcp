import Link from "next/link";

import type { Me } from "@/lib/types";
import { AppNav } from "./AppNav";
import { UserMenu } from "./UserMenu";
import styles from "./AppHeader.module.css";

/**
 * The app shell's top bar: wordmark + primary nav + user menu. Carries a stable
 * `view-transition-name` so it stays anchored (never slides) during route transitions —
 * globals.css suppresses its animation (docs/08 §Anchoring the header).
 */
export function AppHeader({ me }: { me: Me }) {
  return (
    <header className={styles.header} style={{ viewTransitionName: "app-header" }}>
      <div className={styles.inner}>
        <Link href="/library" className={styles.logo} aria-label="Tempo home">
          <span className={styles.mark} aria-hidden />
          Tempo
        </Link>
        <AppNav />
        <UserMenu me={me} />
      </div>
    </header>
  );
}
