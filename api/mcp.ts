import type { IncomingMessage, ServerResponse } from "http";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { registerSessionTools } from "../lib/tools/sessions";
import { registerSetTools } from "../lib/tools/sets";
import { registerPrTools } from "../lib/tools/prs";
import { registerSkillTools } from "../lib/tools/skills";
import { registerAnalyticsTools } from "../lib/tools/analytics";

export const config = { runtime: "nodejs" };

const SERVER_NAME = "workout-tracker";
const SERVER_VERSION = "1.0.0";

function buildServer(): McpServer {
  const server = new McpServer(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: {} } }
  );

  registerSessionTools(server);
  registerSetTools(server);
  registerPrTools(server);
  registerSkillTools(server);
  registerAnalyticsTools(server);

  return server;
}

function isAuthorized(req: IncomingMessage): boolean {
  const expected = process.env.MCP_AUTH_TOKEN;
  if (!expected) return false;

  const header = req.headers["authorization"];
  if (!header || Array.isArray(header)) return false;

  const [scheme, token] = header.split(" ");
  return scheme === "Bearer" && token === expected;
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
    if (!isAuthorized(req)) {
      return sendJson(res, 401, { error: "Unauthorized" });
    }

    const method = (req.method ?? "GET").toUpperCase();

    if (method === "GET") {
      // Server info handshake for the claude.ai connector.
      return sendJson(res, 200, {
        name: SERVER_NAME,
        version: SERVER_VERSION,
        protocol: "mcp",
        transport: "streamable-http",
        capabilities: { tools: {} },
      });
    }

    if (method === "POST") {
      const server = buildServer();
      // Stateless mode: no session persistence between requests.
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
      // Stateless server has nothing to tear down per session.
      return sendJson(res, 200, { ok: true });
    }

    res.statusCode = 405;
    res.setHeader("Allow", "GET, POST, DELETE");
    return sendJson(res, 405, { error: "Method Not Allowed" });
  } catch (err) {
    console.error("api/mcp handler failed", err);
    if (!res.headersSent) {
      return sendJson(res, 500, {
        error: "Internal Server Error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
    res.end();
  }
}
