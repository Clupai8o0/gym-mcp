import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { getSupabase } from "../supabase";
import {
  getSessionFrequencyInput,
  getVolumeSummaryInput,
} from "../schema";
import { ok, fail } from "./shared";

type SetRow = {
  exercise_name: string;
  weight_kg: number | null;
  reps: number | null;
  session: { date: string } | { date: string }[] | null;
};

function mondayOf(date: Date): Date {
  const d = new Date(Date.UTC(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate()
  ));
  const day = d.getUTCDay(); // 0 Sun .. 6 Sat
  const diff = (day === 0 ? -6 : 1 - day);
  d.setUTCDate(d.getUTCDate() + diff);
  return d;
}

export function registerAnalyticsTools(server: McpServer) {
  server.tool(
    "get_volume_summary",
    "Total sets, reps, and tonnage between two dates, grouped by exercise.",
    getVolumeSummaryInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        let query = supabase
          .from("exercise_sets")
          .select(
            "exercise_name, weight_kg, reps, session:workout_sessions!inner(date)"
          )
          .gte("session.date", input.from_date)
          .lte("session.date", input.to_date);

        if (input.exercise_name) {
          query = query.eq("exercise_name", input.exercise_name);
        }

        const { data, error } = await query;
        if (error) throw error;

        type Bucket = {
          exercise_name: string;
          total_sets: number;
          total_reps: number;
          total_tonnage_kg: number | null;
          has_bodyweight_set: boolean;
        };

        const buckets = new Map<string, Bucket>();
        for (const row of (data ?? []) as SetRow[]) {
          const key = row.exercise_name;
          let b = buckets.get(key);
          if (!b) {
            b = {
              exercise_name: key,
              total_sets: 0,
              total_reps: 0,
              total_tonnage_kg: 0,
              has_bodyweight_set: false,
            };
            buckets.set(key, b);
          }

          b.total_sets += 1;
          b.total_reps += row.reps ?? 0;

          if (row.weight_kg === null || row.weight_kg === undefined) {
            b.has_bodyweight_set = true;
          } else if (b.total_tonnage_kg !== null && row.reps !== null) {
            b.total_tonnage_kg += Number(row.weight_kg) * Number(row.reps);
          }
        }

        // If any set in a bucket was bodyweight, tonnage becomes null.
        const summary = [...buckets.values()].map((b) => ({
          exercise_name: b.exercise_name,
          total_sets: b.total_sets,
          total_reps: b.total_reps,
          total_tonnage_kg: b.has_bodyweight_set ? null : b.total_tonnage_kg,
        }));

        return ok({
          from_date: input.from_date,
          to_date: input.to_date,
          summary,
        });
      } catch (err) {
        console.error("get_volume_summary failed", { input, err });
        return fail("get_volume_summary", err);
      }
    }
  );

  server.tool(
    "get_session_frequency",
    "Sessions per ISO week for the last N weeks (default 8).",
    getSessionFrequencyInput,
    async (input) => {
      try {
        const weeks = input.weeks ?? 8;
        const supabase = getSupabase();

        const now = new Date();
        const startMonday = mondayOf(now);
        startMonday.setUTCDate(startMonday.getUTCDate() - 7 * (weeks - 1));

        const { data, error } = await supabase
          .from("workout_sessions")
          .select("date")
          .gte("date", startMonday.toISOString())
          .order("date", { ascending: true });

        if (error) throw error;

        const counts = new Map<string, number>();
        for (let i = 0; i < weeks; i++) {
          const w = new Date(startMonday);
          w.setUTCDate(startMonday.getUTCDate() + 7 * i);
          counts.set(w.toISOString().slice(0, 10), 0);
        }

        for (const row of data ?? []) {
          const w = mondayOf(new Date(row.date)).toISOString().slice(0, 10);
          if (counts.has(w)) counts.set(w, (counts.get(w) ?? 0) + 1);
        }

        const result = [...counts.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([week_start, count]) => ({ week_start, count }));

        return ok({ weeks, frequency: result });
      } catch (err) {
        console.error("get_session_frequency failed", { input, err });
        return fail("get_session_frequency", err);
      }
    }
  );
}
