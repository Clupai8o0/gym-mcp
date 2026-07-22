import { Card } from "@/components/ui";
import { API_URL } from "@/lib/env";
import { CopyButton } from "./CopyButton";
import styles from "./ConnectorCard.module.css";

/**
 * The MCP connector guide (docs/07 §Connected apps): the copy-able `/mcp` URL plus the short
 * "Add Tempo to Claude" steps. Server component — `API_URL` is the public API origin; the copy
 * affordance is the only client bit.
 */
export function ConnectorCard() {
  const mcpUrl = `${API_URL}/mcp`;
  return (
    <Card className={styles.card}>
      <div className={styles.head}>
        <h3 className={styles.title}>Add Tempo to Claude</h3>
        <p className={styles.lede}>
          Connect Tempo as a custom MCP connector to search the library, log workouts, and read your
          progress from chat.
        </p>
      </div>

      <div className={styles.urlRow}>
        <code className={styles.url}>{mcpUrl}</code>
        <CopyButton value={mcpUrl} label="Copy URL" />
      </div>

      <ol className={styles.steps}>
        <li>
          In Claude, open <span className={styles.strong}>Settings → Connectors</span> and choose{" "}
          <span className={styles.strong}>Add custom connector</span>.
        </li>
        <li>Paste the URL above and continue.</li>
        <li>Sign in with Google when prompted to authorize the connection.</li>
      </ol>
    </Card>
  );
}
