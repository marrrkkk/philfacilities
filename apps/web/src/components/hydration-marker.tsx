"use client";

import { useEffect } from "react";

/**
 * Publishes a hydration flag on <html> for end-to-end tests.
 *
 * Server-rendered form controls accept keystrokes before React hydrates, but
 * hydration reconciles uncontrolled inputs back to their defaultValue and can
 * silently discard those keystrokes. Tests that type or click must wait until
 * client components are interactive rather than racing the hydration commit.
 */
export function HydrationMarker() {
  useEffect(() => {
    document.documentElement.dataset.hydrated = "true";
  }, []);

  return null;
}
