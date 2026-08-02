import type { Metadata } from "next";
import { cookies } from "next/headers";

import {
  AccountCard,
  ConnectionsList,
  ConnectorCard,
  ThemeToggle,
  UnitToggle,
} from "@/components/settings";
import { InstallCard } from "@/components/pwa/InstallCard";
import { listConnections } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { THEME_COOKIE, toThemePreference } from "@/lib/theme";
import type { UnitPref } from "@/lib/types";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Settings",
  description: "Units, connected apps, and account.",
};

export default async function SettingsPage() {
  const [me, connections, cookieStore] = await Promise.all([
    requireUser("/settings"),
    listConnections(),
    cookies(),
  ]);
  const unit = me.unit_pref as UnitPref;
  // Read server-side so the control renders already on the stored choice — same trick as the rail.
  const theme = toThemePreference(cookieStore.get(THEME_COOKIE)?.value);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <p className="eyebrow">Account</p>
        <h1 className={styles.title}>Settings</h1>
      </header>

      <InstallCard />

      <section className={styles.section} aria-labelledby="prefs-heading">
        <div className={styles.sectionHead}>
          <h2 id="prefs-heading" className={styles.sectionTitle}>
            Preferences
          </h2>
        </div>

        <div className={styles.fields}>
          <div className={styles.field}>
            <div className={styles.sectionHead}>
              <h3 className={styles.fieldTitle}>Units</h3>
              <p className={styles.sectionLede}>
                Weights are stored in kilograms; this only changes how they&rsquo;re displayed.
              </p>
            </div>
            <UnitToggle current={unit} />
          </div>

          <div className={styles.field}>
            <div className={styles.sectionHead}>
              <h3 className={styles.fieldTitle}>Appearance</h3>
              <p className={styles.sectionLede}>
                Dark is the signature. Pick one, or follow your system — the exercise illustrations
                switch linework to match either way.
              </p>
            </div>
            <ThemeToggle current={theme} />
          </div>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="apps-heading">
        <div className={styles.sectionHead}>
          <h2 id="apps-heading" className={styles.sectionTitle}>
            Connected apps
          </h2>
          <p className={styles.sectionLede}>
            Chat clients connected to Tempo over OAuth. Revoke any you no longer use.
          </p>
        </div>
        <ConnectorCard />
        <ConnectionsList connections={connections.items} />
      </section>

      <section className={styles.section} aria-labelledby="account-heading">
        <div className={styles.sectionHead}>
          <h2 id="account-heading" className={styles.sectionTitle}>
            Account
          </h2>
        </div>
        <AccountCard me={me} />
      </section>
    </div>
  );
}
