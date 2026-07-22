"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { Button, Card } from "@/components/ui";
import styles from "./InstallCard.module.css";

/** The (non-standard but widely-supported) install-prompt event. */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/** Track display-mode + appinstalled so the card hides itself once Tempo is installed. */
function subscribeStandalone(callback: () => void): () => void {
  const mq = window.matchMedia("(display-mode: standalone)");
  window.addEventListener("appinstalled", callback);
  mq.addEventListener("change", callback);
  return () => {
    window.removeEventListener("appinstalled", callback);
    mq.removeEventListener("change", callback);
  };
}
function readStandalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean };
  return window.matchMedia("(display-mode: standalone)").matches || nav.standalone === true;
}

const noopSubscribe = () => () => {};
function readIosSafari(): boolean {
  const ua = navigator.userAgent;
  return /iP(?:hone|ad|od)/.test(ua) && /WebKit/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
}

/**
 * The install affordance (docs/10 Phase 9 "install polish"). On Chromium it captures the deferred
 * `beforeinstallprompt` and offers an Install button; on iOS Safari — which has no such event — it
 * shows the "Add to Home Screen" steps. Renders nothing when already installed (standalone) or when
 * install isn't offered, so it never shows a dead control. Environment reads go through
 * `useSyncExternalStore` (SSR snapshot = not-installed) to stay hydration-safe.
 */
export function InstallCard() {
  const standalone = useSyncExternalStore(subscribeStandalone, readStandalone, () => false);
  const isIosSafari = useSyncExternalStore(noopSubscribe, readIosSafari, () => false);
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPromptEvent(event as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setPromptEvent(null);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  // Show only when there's something actionable: a captured prompt, or iOS Safari's manual steps.
  if (standalone || (!promptEvent && !isIosSafari)) return null;

  const install = async () => {
    if (!promptEvent) return;
    await promptEvent.prompt();
    await promptEvent.userChoice;
    setPromptEvent(null);
  };

  return (
    <Card className={styles.card}>
      <div className={styles.text}>
        <p className={styles.title}>Install Tempo</p>
        <p className={styles.body}>
          {promptEvent
            ? "Add Tempo to your device for a full-screen, offline-ready app that keeps logging at the gym."
            : "Tap the Share button, then “Add to Home Screen”, to install Tempo as an app."}
        </p>
      </div>
      {promptEvent && (
        <Button variant="outline" onClick={install}>
          Install
        </Button>
      )}
    </Card>
  );
}
