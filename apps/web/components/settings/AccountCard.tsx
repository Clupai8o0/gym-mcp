"use client";

import { useState } from "react";

import { Button, Card } from "@/components/ui";
import { API_URL, CLIENT_HEADER } from "@/lib/env";
import { formatDate } from "@/lib/format";
import type { Me } from "@/lib/types";
import styles from "./AccountCard.module.css";

/** The signed-in identity + sign-out (Settings → account, docs/07). Sign-out mirrors the header. */
export function AccountCard({ me }: { me: Me }) {
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
      // Ignore network errors — redirecting home is enough to end the client session.
    }
    window.location.href = "/";
  };

  const initial = (me.name?.trim() || me.email).slice(0, 1).toUpperCase();

  return (
    <Card className={styles.card}>
      <div className={styles.identity}>
        {me.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- tiny external avatar, not LCP
          <img src={me.avatar_url} alt="" className={styles.avatar} width={44} height={44} />
        ) : (
          <span className={styles.initials} aria-hidden>
            {initial}
          </span>
        )}
        <div className={styles.meta}>
          <span className={styles.name}>{me.name ?? me.email}</span>
          <span className={styles.email}>{me.email}</span>
          <span className={styles.since}>Member since {formatDate(me.created_at)}</span>
        </div>
      </div>
      <Button variant="outline" onClick={signOut} loading={busy}>
        Sign out
      </Button>
    </Card>
  );
}
