import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { getSupabase } from "../supabase";
import { getSessionSetsInput, logSetInput } from "../schema";
import { ok, fail } from "./shared";

type DetectedPr = {
  is_pr: boolean;
  pr_type: "weight" | "reps" | "hold_time" | "first_log" | null;
  previous_best: number | null;
  new_value: number | null;
};

type LogSetInput = {
  session_id: string;
  exercise_name: string;
  set_number: number;
  weight_kg?: number;
  reps?: number;
  hold_seconds?: number;
  rpe?: number;
  notes?: string;
};

async function detectPr(input: LogSetInput): Promise<DetectedPr> {
  const supabase = getSupabase();

  const { data: existing, error } = await supabase
    .from("personal_records")
    .select("pr_type, value")
    .eq("exercise_name", input.exercise_name);

  if (error) throw error;

  const records = new Map<string, number>();
  for (const r of existing ?? []) records.set(r.pr_type, Number(r.value));

  // Hold-time PR
  if (input.hold_seconds !== undefined && input.hold_seconds !== null) {
    const best = records.get("hold_time");
    if (best === undefined || input.hold_seconds > best) {
      return {
        is_pr: true,
        pr_type: "hold_time",
        previous_best: best ?? null,
        new_value: input.hold_seconds,
      };
    }
  }

  // Weight / reps PR
  if (
    input.weight_kg !== undefined &&
    input.weight_kg !== null &&
    input.reps !== undefined &&
    input.reps !== null
  ) {
    const bestWeight = records.get("weight");
    if (bestWeight === undefined || input.weight_kg > bestWeight) {
      return {
        is_pr: true,
        pr_type: "weight",
        previous_best: bestWeight ?? null,
        new_value: input.weight_kg,
      };
    }

    const bestReps = records.get("reps");
    if (bestReps === undefined || input.reps > bestReps) {
      return {
        is_pr: true,
        pr_type: "reps",
        previous_best: bestReps ?? null,
        new_value: input.reps,
      };
    }
  }

  // First log for this exercise
  if ((existing?.length ?? 0) === 0) {
    const first =
      input.weight_kg ?? input.reps ?? input.hold_seconds ?? null;
    if (first !== null) {
      return {
        is_pr: true,
        pr_type: "first_log",
        previous_best: null,
        new_value: first,
      };
    }
  }

  return { is_pr: false, pr_type: null, previous_best: null, new_value: null };
}

async function upsertPersonalRecord(
  exercise_name: string,
  pr_type: "weight" | "reps" | "hold_time" | "first_log",
  value: number,
  session_id: string
) {
  const supabase = getSupabase();

  // 'first_log' is recorded on the set but stored as the appropriate concrete
  // pr_type so future comparisons can use it. Pick weight if available, else
  // reps, else hold_time. The caller already chose `value` accordingly.
  const concrete: "weight" | "reps" | "hold_time" =
    pr_type === "first_log" ? "weight" : pr_type;

  const { error } = await supabase
    .from("personal_records")
    .upsert(
      {
        exercise_name,
        pr_type: concrete,
        value,
        achieved_at: new Date().toISOString(),
        session_id,
      },
      { onConflict: "exercise_name,pr_type" }
    );

  if (error) throw error;
}

export function registerSetTools(server: McpServer) {
  server.tool(
    "log_set",
    "Log a single set within a session. Auto-detects PRs and updates personal_records.",
    logSetInput,
    async (input) => {
      try {
        const pr = await detectPr(input);

        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("exercise_sets")
          .insert({
            session_id: input.session_id,
            exercise_name: input.exercise_name,
            set_number: input.set_number,
            weight_kg: input.weight_kg ?? null,
            reps: input.reps ?? null,
            hold_seconds: input.hold_seconds ?? null,
            rpe: input.rpe ?? null,
            notes: input.notes ?? null,
            is_pr: pr.is_pr,
            pr_type: pr.pr_type,
          })
          .select("id")
          .single();

        if (error) throw error;

        if (pr.is_pr && pr.pr_type && pr.new_value !== null) {
          // For first_log, decide which concrete pr_type to record under.
          let concrete: "weight" | "reps" | "hold_time";
          let value: number;
          if (pr.pr_type === "first_log") {
            if (input.weight_kg !== undefined && input.weight_kg !== null) {
              concrete = "weight";
              value = input.weight_kg;
            } else if (input.reps !== undefined && input.reps !== null) {
              concrete = "reps";
              value = input.reps;
            } else {
              concrete = "hold_time";
              value = input.hold_seconds ?? 0;
            }
          } else {
            concrete = pr.pr_type;
            value = pr.new_value;
          }

          await upsertPersonalRecord(
            input.exercise_name,
            concrete,
            value,
            input.session_id
          );
        }

        return ok({
          set_id: data.id,
          is_pr: pr.is_pr,
          pr_type: pr.pr_type,
          previous_best: pr.previous_best,
        });
      } catch (err) {
        console.error("log_set failed", { input, err });
        return fail("log_set", err);
      }
    }
  );

  server.tool(
    "get_session_sets",
    "Return all sets for a session grouped by exercise name and ordered by set_number.",
    getSessionSetsInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("exercise_sets")
          .select("*")
          .eq("session_id", input.session_id)
          .order("exercise_name", { ascending: true })
          .order("set_number", { ascending: true });

        if (error) throw error;

        const grouped: Record<string, typeof data> = {};
        for (const s of data ?? []) {
          (grouped[s.exercise_name] ||= []).push(s);
        }

        return ok({ sets_by_exercise: grouped });
      } catch (err) {
        console.error("get_session_sets failed", { input, err });
        return fail("get_session_sets", err);
      }
    }
  );
}
