import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { getSupabase } from "../supabase";
import { getPrHistoryInput, getPrsInput, logPrInput } from "../schema";
import { ok, fail } from "./shared";

export function registerPrTools(server: McpServer, userId: string) {
  server.tool(
    "get_prs",
    "Return all personal records, optionally filtered by exercise name.",
    getPrsInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        let query = supabase
          .from("personal_records")
          .select("*")
          .eq("user_id", userId)
          .order("exercise_name", { ascending: true });

        if (input.exercise_name) {
          query = query.eq("exercise_name", input.exercise_name);
        }

        const { data, error } = await query;
        if (error) throw error;

        return ok({ prs: data ?? [] });
      } catch (err) {
        console.error("get_prs failed", { input, err });
        return fail("get_prs", err);
      }
    }
  );

  server.tool(
    "get_pr_history",
    "Chronological list of PR sets for a given exercise and pr_type.",
    getPrHistoryInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("exercise_sets")
          .select(
            "id, exercise_name, set_number, weight_kg, reps, hold_seconds, pr_type, notes, created_at, session:workout_sessions(id, date, session_type)"
          )
          .eq("user_id", userId)
          .eq("exercise_name", input.exercise_name)
          .eq("is_pr", true)
          .eq("pr_type", input.pr_type)
          .order("created_at", { ascending: true });

        if (error) throw error;

        return ok({ history: data ?? [] });
      } catch (err) {
        console.error("get_pr_history failed", { input, err });
        return fail("get_pr_history", err);
      }
    }
  );

  server.tool(
    "log_pr",
    "Manually upsert a personal record (skill holds, first attempts, etc.).",
    logPrInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("personal_records")
          .upsert(
            {
              user_id: userId,
              exercise_name: input.exercise_name,
              pr_type: input.pr_type,
              value: input.value,
              achieved_at: input.achieved_at,
              session_id: input.session_id ?? null,
              notes: input.notes ?? null,
            },
            { onConflict: "exercise_name,pr_type,user_id" }
          )
          .select("*")
          .single();

        if (error) throw error;
        return ok({ pr: data });
      } catch (err) {
        console.error("log_pr failed", { input, err });
        return fail("log_pr", err);
      }
    }
  );
}
