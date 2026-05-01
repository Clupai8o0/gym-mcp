import type { IncomingMessage, ServerResponse } from "http";
import { randomBytes } from "crypto";
import { getSupabase } from "../../lib/supabase";

export const config = { runtime: "nodejs" };

function sendJson(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

function isAuthorized(req: IncomingMessage): boolean {
  const adminSecret = process.env.ADMIN_SECRET;
  if (!adminSecret) return false;
  const header = req.headers["authorization"];
  if (!header || Array.isArray(header)) return false;
  const [scheme, secret] = header.split(" ");
  return scheme === "Bearer" && secret === adminSecret;
}

async function readBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      if (chunks.length === 0) return resolve({});
      try {
        const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        resolve(typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {});
      } catch {
        resolve({});
      }
    });
    req.on("error", reject);
  });
}

export default async function handler(
  req: IncomingMessage,
  res: ServerResponse
) {
  const method = (req.method ?? "GET").toUpperCase();

  // ── GET /api/admin/token — diagnostics ──────────────────────────────────
  if (method === "GET") {
    if (!isAuthorized(req)) return sendJson(res, 401, { error: "Unauthorized" });

    const supabaseUrl = process.env.SUPABASE_URL ?? "(not set)";
    const hasKey = !!process.env.SUPABASE_SERVICE_ROLE_KEY;
    const projectRef = supabaseUrl.match(/https:\/\/([^.]+)\.supabase\.co/)?.[1] ?? "unknown";

    const results: Record<string, unknown> = {
      supabase_url: supabaseUrl,
      project_ref: projectRef,
      has_service_role_key: hasKey,
    };

    try {
      const supabase = getSupabase();

      // Test 1: can we reach Supabase at all?
      const t1 = await supabase.from("workout_sessions").select("id").limit(1);
      results["test_workout_sessions_select"] = t1.error
        ? { error: t1.error.code, message: t1.error.message }
        : "ok";

      // Test 2: can we reach access_tokens?
      const t2 = await supabase.from("access_tokens").select("id").limit(1);
      results["test_access_tokens_select"] = t2.error
        ? { error: t2.error.code, message: t2.error.message }
        : "ok";

      // Test 3: raw insert attempt with no .select()
      const testToken = "diag_" + randomBytes(4).toString("hex");
      const t3 = await supabase
        .from("access_tokens")
        .insert({ token: testToken, user_id: "diag", name: "diag", is_beta: false });
      results["test_access_tokens_insert"] = t3.error
        ? { error: t3.error.code, message: t3.error.message }
        : "ok";

      // Clean up the test row
      if (!t3.error) {
        await supabase.from("access_tokens").delete().eq("token", testToken);
      }
    } catch (err) {
      results["exception"] = err instanceof Error ? err.message : JSON.stringify(err);
    }

    return sendJson(res, 200, results);
  }

  // ── POST /api/admin/token — create token ────────────────────────────────
  if (method === "POST") {
    try {
      if (!process.env.ADMIN_SECRET) {
        return sendJson(res, 503, { error: "Admin endpoint not configured" });
      }
      if (!isAuthorized(req)) {
        return sendJson(res, 401, { error: "Unauthorized" });
      }

      const body = await readBody(req);
      const name = typeof body.name === "string" ? body.name : null;
      const userId =
        typeof body.user_id === "string" && body.user_id.length > 0
          ? body.user_id
          : randomBytes(8).toString("hex");
      const isBeta = body.is_beta !== false;

      const token = "gym_" + randomBytes(32).toString("hex");

      const supabase = getSupabase();

      console.log("Inserting token for user:", userId);

      const { data, error } = await supabase
        .from("access_tokens")
        .insert({ token, user_id: userId, name, is_beta: isBeta })
        .select("id, user_id, name, is_beta, created_at")
        .single();

      if (error) throw error;

      return sendJson(res, 201, {
        token,
        user_id: data.user_id,
        name: data.name,
        is_beta: data.is_beta,
        created_at: data.created_at,
      });
    } catch (err) {
      console.error("api/admin/token POST failed", err);
      return sendJson(res, 500, {
        error: "Internal Server Error",
        message: err instanceof Error ? err.message : JSON.stringify(err),
      });
    }
  }

  res.setHeader("Allow", "GET, POST");
  return sendJson(res, 405, { error: "Method Not Allowed" });
}
