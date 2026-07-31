import Link from "next/link";

import { LocalTime } from "@/components/ui";
import type { Me } from "@/lib/types";
import styles from "./HomeHeader.module.css";

export interface HomeHeaderProps {
  me: Me;
  /** The server's "now" — rendered in the viewer's timezone by `LocalTime`. */
  now: string;
  /** Desktop-only slot beside the avatar (the range control). Hidden below 768px. */
  action?: React.ReactNode;
}

/**
 * The home screen's title row: today's date and a tap-target through to the account. Deliberately
 * one line on a phone — the workout below it is what the screen is for, and it must never sit
 * below the fold (docs `HANDOVER-mobile-first` §11C). It scrolls away with the content; there is
 * no sticky header. On desktop it grows into the page's masthead and takes the range control.
 */
export function HomeHeader({ me, now, action }: HomeHeaderProps) {
  const initial = (me.name?.trim() || me.email).slice(0, 1).toUpperCase();
  const first = me.name?.trim().split(/\s+/)[0];

  return (
    <header className={styles.head}>
      <div className={styles.text}>
        <LocalTime iso={now} format="day" className="eyebrow" />
        <h1 className={styles.title}>{first ? `Hey, ${first}` : "Today"}</h1>
      </div>
      <div className={styles.actions}>
        {action && <div className={styles.action}>{action}</div>}
        <Link href="/settings" className={styles.avatarLink} aria-label="Account and settings">
          {me.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- tiny external avatar, not LCP
            <img src={me.avatar_url} alt="" className={styles.avatar} width={36} height={36} />
          ) : (
            <span className={styles.initials} aria-hidden>
              {initial}
            </span>
          )}
        </Link>
      </div>
    </header>
  );
}
