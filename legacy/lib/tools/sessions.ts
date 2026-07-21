import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { getSupabase } from "../supabase";
import {
  getSessionInput,
  listSessionsInput,
  logSessionInput,
} from "../schema";
import { ok, fail } from "./shared";

export function registerSessionTools(server: McpServer, userId: string) {
  server.tool(
    "log_session",
    "Create a new workout session.",
    logSessionInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("workout_sessions")
          .insert({
            user_id: userId,
            session_type: input.session_type,
            date: input.date,
            notes: input.notes ?? null,
            duration_minutes: input.duration_minutes ?? null,
          })
          .select("id, session_type, date")
          .single();

        if (error) throw error;

        return ok({
          session_id: data.id,
          session_type: data.session_type,
          date: data.date,
        });
      } catch (err) {
        console.error("log_session failed", { input, err });
        return fail("log_session", err);
      }
    }
  );

  server.tool(
    "get_session",
    "Fetch a workout session by ID along with all sets grouped by exercise.",
    getSessionInput,
    async (input) => {
      try {
        const supabase = getSupabase();

        const { data: session, error: sErr } = await supabase
          .from("workout_sessions")
          .select("*")
          .eq("id", input.session_id)
          .eq("user_id", userId)
          .single();

        if (sErr) throw sErr;
        if (!session) {
          return ok({ session: null, sets_by_exercise: {} });
        }

        const { data: sets, error: setsErr } = await supabase
          .from("exercise_sets")
          .select("*")
          .eq("session_id", input.session_id)
          .eq("user_id", userId)
          .order("exercise_name", { ascending: true })
          .order("set_number", { ascending: true });

        if (setsErr) throw setsErr;

        const grouped: Record<string, typeof sets> = {};
        for (const s of sets ?? []) {
          (grouped[s.exercise_name] ||= []).push(s);
        }

        return ok({ session, sets_by_exercise: grouped });
      } catch (err) {
        console.error("get_session failed", { input, err });
        return fail("get_session", err);
      }
    }
  );

  server.tool(
    "list_sessions",
    "List workout sessions with optional filters and pagination.",
    listSessionsInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        const limit = input.limit ?? 20;
        const offset = input.offset ?? 0;

        let query = supabase
          .from("workout_sessions")
          .select("*", { count: "exact" })
          .eq("user_id", userId)
          .order("date", { ascending: false })
          .range(offset, offset + limit - 1);

        if (input.session_type) query = query.eq("session_type", input.session_type);
        if (input.from_date) query = query.gte("date", input.from_date);
        if (input.to_date) query = query.lte("date", input.to_date);

        const { data, count, error } = await query;
        if (error) throw error;

        return ok({
          sessions: data ?? [],
          total: count ?? 0,
          limit,
          offset,
        });
      } catch (err) {
        console.error("list_sessions failed", { input, err });
        return fail("list_sessions", err);
      }
    }
  );
}
