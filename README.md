# Workout Tracker MCP

A Vercel-deployable MCP (Model Context Protocol) server that exposes a
Supabase-backed workout tracker over Streamable HTTP. Connects directly to
Claude.ai via the MCP Connector UI.

The server tracks workout sessions, exercise sets, personal records (with
auto-detection), and skill progressions for a powerbuilding / calisthenics
training plan.

## 1. Supabase Setup

1. Create a new project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** and run the contents of `supabase/migrations/001_init.sql`
3. Go to **Settings → API** and copy:
   - `Project URL` → this is your `SUPABASE_URL`
   - `service_role` key → this is your `SUPABASE_SERVICE_ROLE_KEY`

## 2. Vercel Deploy

```bash
npm i -g vercel
vercel login
vercel env add SUPABASE_URL
vercel env add SUPABASE_SERVICE_ROLE_KEY
vercel env add MCP_AUTH_TOKEN   # generate with: openssl rand -hex 32
vercel deploy --prod
```

Your MCP endpoint will be: `https://<your-project>.vercel.app/api/mcp`

## 3. Connect to Claude.ai

1. Go to **claude.ai → Settings → Integrations**
2. Click **Add MCP Server**
3. Fill in:
   - **Name**: Workout Tracker
   - **URL**: `https://<your-project>.vercel.app/api/mcp`
   - **Auth header**: `Authorization: Bearer <your MCP_AUTH_TOKEN>`
4. Click **Connect**

Claude will now have access to all workout tracking tools in every conversation.

## 4. Verify the Endpoint

Before connecting in Claude.ai, confirm the server responds:

```bash
curl -H "Authorization: Bearer <your_token>" \
  https://<your-project>.vercel.app/api/mcp
```

A successful response returns the MCP server info JSON. A 401 means your token
is wrong. A 500 means check Vercel function logs for a Supabase connection
error.

## 5. Example Tool Calls

Once connected, you can say to Claude:

> "Log an upper power session for today"
> "Log a bench press set: 90kg × 5 reps at RPE 8"
> "Did I hit any PRs this week?"
> "Update my planche progress to stage 3 at 60%"
> "Show me my skill overview"
> "What's my volume for the last 4 weeks?"

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| Connector shows "failed to connect" | Run the curl test above. Check Vercel env vars are set. |
| 401 on all requests | Re-add `MCP_AUTH_TOKEN` in Vercel dashboard → Redeploy |
| PRs not auto-detecting | Confirm `SUPABASE_SERVICE_ROLE_KEY` is set (anon key won't have write access) |
| Tool calls return empty data | Check Supabase SQL editor — confirm migration ran and tables exist |

## Environment Variables

| Variable | Description |
|---|---|
| `SUPABASE_URL` | From Supabase project settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (not anon) — required for server-side writes |
| `MCP_AUTH_TOKEN` | Any strong random string — used to protect the public endpoint |

## Tools

### Sessions
- `log_session` — create a new workout session
- `get_session` — fetch one session and its sets grouped by exercise
- `list_sessions` — paginated session list with optional filters

### Sets
- `log_set` — log a set; auto-detects PRs and updates `personal_records`
- `get_session_sets` — sets for a session, grouped by exercise

### PRs
- `get_prs` — all PRs, optionally filtered by exercise
- `get_pr_history` — chronological PR history for an exercise + pr_type
- `log_pr` — manually upsert a PR

### Skills
- `update_skill_progress` — upsert progress for a skill
- `get_skill_overview` — progress for all 13 tracked skills (seeded)
- `get_skill_detail` — progress + total stage count for one skill

### Analytics
- `get_volume_summary` — total sets, reps, and tonnage between two dates
- `get_session_frequency` — sessions per ISO week for the last N weeks
