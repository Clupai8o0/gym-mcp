import Link from "next/link";

import { LocalTime } from "@/components/ui";
import type { Me } from "@/lib/types";
import styles from "./HomeHeader.module.css";

/**
 * The home screen's title row: today's date and a tap-target through to the account. Deliberately
 * one line — the workout below it is what the screen is for, and it must never sit below the fold
 * (docs `HANDOVER-mobile-first` §11C). It scrolls away with the content; there is no sticky header.
 */
export function HomeHeader({ me, now }: { me: Me; now: string }) {
  const initial = (me.name?.trim() || me.email).slice(0, 1).toUpperCase();
  const first = me.name?.trim().split(/\s+/)[0];

  return (
    <header className={styles.head}>
      <div className={styles.text}>
        <LocalTime iso={now} format="day" className="eyebrow" />
        <h1 className={styles.title}>{first ? `Hey, ${first}` : "Today"}</h1>
      </div>
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
    </header>
  );
}
