"use client";

import { useState } from "react";

import { Button } from "@/components/ui";

/** Copy a value to the clipboard, briefly confirming. Falls back silently if clipboard is blocked. */
export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard unavailable (permissions/insecure context) — leave the label unchanged.
    }
  };

  return (
    <Button variant="outline" size="sm" onClick={copy} aria-live="polite">
      {copied ? "Copied" : label}
    </Button>
  );
}
