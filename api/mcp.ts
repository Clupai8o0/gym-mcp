import type { IncomingMessage, ServerResponse } from "http";
import { parse as parseUrl } from "url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { getSupabase } from "../lib/supabase";
import { GUIDE } from "../lib/guide";
import { registerSessionTools } from "../lib/tools/sessions";
import { registerSetTools } from "../lib/tools/sets";
import { registerPrTools } from "../lib/tools/prs";
import { registerSkillTools } from "../lib/tools/skills";
import { registerAnalyticsTools } from "../lib/tools/analytics";

export const config = { runtime: "nodejs" };

const SERVER_NAME = "workout-tracker";
const SERVER_VERSION = "1.0.0";

function buildServer(userId: string): McpServer {
  const server = new McpServer(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: {}, resources: {} } }
  );

  server.resource(
    "guide",
    "gym://guide",
    { mimeType: "text/markdown", description: "Full tool reference and workflow guide for this MCP server." },
    async () => ({
      contents: [{ uri: "gym://guide", mimeType: "text/markdown", text: GUIDE }],
    })
  );

  registerSessionTools(server, userId);
  registerSetTools(server, userId);
  registerPrTools(server, userId);
  registerSkillTools(server, userId);
  registerAnalyticsTools(server, userId);

  return server;
}

function extractToken(req: IncomingMessage): string | null {
  const { query } = parseUrl(req.url ?? "", true);
  return typeof query.api_key === "string" && query.api_key ? query.api_key : null;
}

async function resolveUser(req: IncomingMessage): Promise<string | null> {
  const token = extractToken(req);
  if (!token) return null;

  const supabase = getSupabase();
  const { data, error } = await supabase
    .from("access_tokens")
    .select("user_id, is_beta")
    .eq("token", token)
    .single();

  if (error || !data || !data.is_beta) return null;
  return data.user_id as string;
}

function sendJson(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

async function readBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      if (chunks.length === 0) return resolve(undefined);
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch (err) {
        reject(err);
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
    const method = (req.method ?? "GET").toUpperCase();

    if (method === "GET") {
      return sendJson(res, 200, {
        name: SERVER_NAME,
        version: SERVER_VERSION,
        protocol: "mcp",
        transport: "streamable-http",
        capabilities: { tools: {} },
      });
    }

    const userId = await resolveUser(req);
    if (!userId) {
      return sendJson(res, 401, { error: "Unauthorized" });
    }

    if (method === "POST") {
      const server = buildServer(userId);
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
      });

      res.on("close", () => {
        transport.close().catch(() => {});
        server.close().catch(() => {});
      });

      await server.connect(transport);

      const body = await readBody(req);
      await transport.handleRequest(req, res, body);
      return;
    }

    if (method === "DELETE") {
      return sendJson(res, 200, { ok: true });
    }

    res.setHeader("Allow", "GET, POST, DELETE");
    return sendJson(res, 405, { error: "Method Not Allowed" });
  } catch (err) {
    console.error("api/mcp handler failed", err);
    if (!res.headersSent) {
      return sendJson(res, 500, {
        error: "Internal Server Error",
        message: err instanceof Error ? err.message : JSON.stringify(err),
      });
    }
    res.end();
  }
}
