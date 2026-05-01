import type { IncomingMessage, ServerResponse } from "http";
import { randomBytes } from "crypto";
import { getSupabase } from "../../lib/supabase";

export const config = { runtime: "nodejs" };

function sendJson(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
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
  try {
    if ((req.method ?? "GET").toUpperCase() !== "POST") {
      res.setHeader("Allow", "POST");
      return sendJson(res, 405, { error: "Method Not Allowed" });
    }

    const adminSecret = process.env.ADMIN_SECRET;
    if (!adminSecret) {
      return sendJson(res, 503, { error: "Admin endpoint not configured" });
    }

    const authHeader = req.headers["authorization"];
    if (!authHeader || Array.isArray(authHeader)) {
      return sendJson(res, 401, { error: "Unauthorized" });
    }

    const [scheme, secret] = authHeader.split(" ");
    if (scheme !== "Bearer" || secret !== adminSecret) {
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
    const { data, error } = await supabase
      .from("api_tokens")
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
    console.error("api/admin/token failed", err);
    return sendJson(res, 500, {
      error: "Internal Server Error",
      message: err instanceof Error ? err.message : JSON.stringify(err),
    });
  }
}
