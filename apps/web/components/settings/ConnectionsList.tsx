"use client";

import { useEffect, useRef, useState } from "react";

import { Badge, Button, Card, EmptyState } from "@/components/ui";
import { ClientApiError, NetworkError, revokeConnection } from "@/lib/client";
import { formatRelativeDate } from "@/lib/format";
import type { Connection } from "@/lib/types";
import styles from "./ConnectionsList.module.css";

/**
 * The user's connected OAuth apps with a revoke action (docs/07 §Connected apps). Revoke is a
 * two-step inline confirm (destructive; no native dialog per the harness rules), then removes the
 * row optimistically once the API confirms the tokens are revoked. Empty state when nothing's linked.
 */
export function ConnectionsList({ connections }: { connections: Connection[] }) {
  const [items, setItems] = useState(connections);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  // When the destructive confirm appears, move focus to the safe default (Cancel) so keyboard/SR
  // users land on it rather than dropping to <body> as the trigger button unmounts.
  useEffect(() => {
    if (confirming) cancelRef.current?.focus();
  }, [confirming]);

  const revoke = async (clientId: string) => {
    setBusy(clientId);
    setError(null);
    try {
      await revokeConnection(clientId);
      setItems((prev) => prev.filter((item) => item.client_id !== clientId));
      setConfirming(null);
    } catch (caught) {
      if (caught instanceof NetworkError) {
        setError("You appear to be offline — couldn't revoke. Try again.");
      } else if (caught instanceof ClientApiError) {
        setError(caught.message);
      } else {
        throw caught;
      }
    } finally {
      setBusy(null);
    }
  };

  if (items.length === 0) {
    return (
      <EmptyState
        title="No connected apps"
        description="When you connect Tempo to Claude or another MCP client, it'll appear here — and you can revoke it any time."
      />
    );
  }

  return (
    <div className={styles.list}>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {items.map((connection) => (
        <Card key={connection.client_id} className={styles.row}>
          <div className={styles.main}>
            <div className={styles.head}>
              <span className={styles.name}>{connection.client_name ?? "Unnamed client"}</span>
              {connection.active_token_count > 0 && <Badge tone="accent">Active</Badge>}
            </div>
            <p className={styles.meta}>
              Connected {formatRelativeDate(connection.connected_at)}
              {connection.last_active_at && (
                <> · last used {formatRelativeDate(connection.last_active_at)}</>
              )}
            </p>
          </div>

          {confirming === connection.client_id ? (
            <div className={styles.confirm}>
              <span className={styles.confirmText} role="alert">
                Revoke access?
              </span>
              <Button
                ref={cancelRef}
                variant="ghost"
                size="sm"
                onClick={() => setConfirming(null)}
                disabled={busy === connection.client_id}
              >
                Cancel
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => revoke(connection.client_id)}
                loading={busy === connection.client_id}
                className={styles.danger}
              >
                Revoke
              </Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setConfirming(connection.client_id)}>
              Revoke
            </Button>
          )}
        </Card>
      ))}
    </div>
  );
}
