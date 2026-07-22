"use client";

import Link from "next/link";
import { useState } from "react";

import { API_URL, CLIENT_HEADER } from "@/lib/env";
import type { Me } from "@/lib/types";
import styles from "./UserMenu.module.css";

/** Initials fallback when there's no avatar. */
function initials(me: Me): string {
  const base = me.name?.trim() || me.email;
  return base.slice(0, 1).toUpperCase();
}

/**
 * The signed-in user's avatar + sign-out. Sign-out POSTs to the API's `/oauth/logout` with the
 * CSRF header + credentials (docs/05), then returns to the landing page.
 */
export function UserMenu({ me }: { me: Me }) {
  const [busy, setBusy] = useState(false);

  const signOut = async () => {
    setBusy(true);
    try {
      await fetch(`${API_URL}/oauth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { [CLIENT_HEADER]: "web" },
      });
    } catch {
      // Ignore network errors — clearing client state and redirecting is enough.
    }
    window.location.href = "/";
  };

  return (
    <div className={styles.menu}>
      <Link href="/settings" className={styles.identity} aria-label="Settings" title="Settings">
        {me.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- tiny external avatar, not LCP
          <img src={me.avatar_url} alt="" className={styles.avatar} width={28} height={28} />
        ) : (
          <span className={styles.initials} aria-hidden>
            {initials(me)}
          </span>
        )}
        <span className={styles.name}>{me.name ?? me.email}</span>
      </Link>
      <button type="button" className={styles.signOut} onClick={signOut} disabled={busy}>
        Sign out
      </button>
    </div>
  );
}
