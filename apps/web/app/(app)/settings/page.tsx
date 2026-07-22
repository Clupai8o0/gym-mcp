import type { Metadata } from "next";

import { AccountCard, ConnectionsList, ConnectorCard, UnitToggle } from "@/components/settings";
import { listConnections } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import type { UnitPref } from "@/lib/types";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Settings",
  description: "Units, connected apps, and account.",
};

export default async function SettingsPage() {
  const [me, connections] = await Promise.all([requireUser("/settings"), listConnections()]);
  const unit = me.unit_pref as UnitPref;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <p className="eyebrow">Account</p>
        <h1 className={styles.title}>Settings</h1>
      </header>

      <section className={styles.section} aria-labelledby="prefs-heading">
        <div className={styles.sectionHead}>
          <h2 id="prefs-heading" className={styles.sectionTitle}>
            Preferences
          </h2>
          <p className={styles.sectionLede}>
            Weights are stored in kilograms; this only changes how they&rsquo;re displayed.
          </p>
        </div>
        <UnitToggle current={unit} />
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
