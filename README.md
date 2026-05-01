# Workout Tracker MCP

A Vercel-deployable MCP server backed by Supabase. Tracks workout sessions,
exercise sets, personal records (auto-detected), and calisthenics skill
progressions. Multi-user with beta-gated API key auth.

---

## 1. Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Open **SQL Editor** and run both migrations in order:
   - `supabase/migrations/001_init.sql`
   - `supabase/migrations/002_multi_user.sql`
3. Go to **Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **service_role** key → `SUPABASE_SERVICE_ROLE_KEY`

---

## 2. Deploy to Vercel

```bash
npm i -g vercel
vercel login

# Add the three required env vars
vercel env add SUPABASE_URL
vercel env add SUPABASE_SERVICE_ROLE_KEY
vercel env add ADMIN_SECRET          # any strong random string, e.g: openssl rand -hex 32

vercel deploy --prod
```

---

## 3. Get Your First API Key

After deploying, call the admin endpoint once to generate your key:

```bash
curl -X POST https://<your-project>.vercel.app/api/admin/token \
  -H "Authorization: Bearer <your ADMIN_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"name": "me", "user_id": "me"}'
```

Response:
```json
{
  "token": "gym_abc123...",
  "user_id": "me",
  "name": "me",
  "is_beta": true
}
```

Save the `token` — this is your API key. You'll append it to the MCP URL as
`?api_key=gym_abc123...`

To create a key for another user, repeat with a different `name` and `user_id`.
Each user's data is fully isolated.

---

## 4. Connect to Claude

The MCP endpoint is:
```
https://<your-project>.vercel.app/api/mcp?api_key=<token>
```

### claude.ai
Settings → Integrations → Add MCP Server
- **URL**: `https://<your-project>.vercel.app/api/mcp?api_key=gym_abc123...`

### Claude Mobile
Same as claude.ai — uses your account's integrations automatically.

### Claude Code (CLI)
```bash
claude mcp add --transport http workout-tracker \
  "https://<your-project>.vercel.app/api/mcp?api_key=gym_abc123..."
```

### Claude Desktop
Claude Desktop requires a local stdio proxy. Add to
`~/Library/Application Support/Claude/claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "workout-tracker": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://<your-project>.vercel.app/api/mcp?api_key=gym_abc123..."
      ]
    }
  }
}
```

---

## 5. Verify the Endpoint

```bash
# Should return server info JSON (no auth needed for GET)
curl https://<your-project>.vercel.app/api/mcp
```

---

## Environment Variables

| Variable | Where to get it | Required |
|---|---|---|
| `SUPABASE_URL` | Supabase → Settings → API → Project URL | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Settings → API → service_role key | Yes |
| `ADMIN_SECRET` | Any random string — `openssl rand -hex 32` | Yes |

> **Note:** Use `service_role` key, not `anon`. The anon key lacks write permissions.

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `curl /api/mcp` returns 500 | Check `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set in Vercel → Redeploy |
| Tool calls return 401 | Token is wrong or `is_beta` is false — re-generate with admin endpoint |
| `api/admin/token` returns 503 | `ADMIN_SECRET` env var is missing |
| `api/admin/token` returns 401 | Wrong `ADMIN_SECRET` value in the curl command |
| PRs not auto-detecting | Confirm `SUPABASE_SERVICE_ROLE_KEY` is set (not anon key) |
| Tool calls return empty data | Confirm both SQL migrations ran in Supabase SQL Editor |

---

## Tools

### Sessions
- `log_session` — create a new workout session
- `get_session` — fetch a session and its sets grouped by exercise
- `list_sessions` — paginated list with optional type/date filters

### Sets
- `log_set` — log a set; auto-detects and saves PRs
- `get_session_sets` — all sets for a session grouped by exercise

### Personal Records
- `get_prs` — all PRs, optionally filtered by exercise
- `get_pr_history` — chronological PR history for an exercise + type
- `log_pr` — manually upsert a PR

### Skills
- `update_skill_progress` — upsert progress for a skill
- `get_skill_overview` — all 13 tracked skills at once
- `get_skill_detail` — progress + total stage count for one skill

### Analytics
- `get_volume_summary` — sets, reps, and tonnage grouped by exercise for a date range
- `get_session_frequency` — sessions per ISO week for the last N weeks

Full tool reference: `https://<your-project>.vercel.app/llm-guide.md`
