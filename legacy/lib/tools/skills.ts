import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { getSupabase } from "../supabase";
import { getSkillDetailInput, updateSkillProgressInput } from "../schema";
import { ok, fail } from "./shared";

export const SEED_SKILLS = [
  "one_arm_pull_up",
  "human_flag",
  "one_arm_push_up",
  "one_arm_handstand",
  "shrimp_squat",
  "hefesto",
  "dragon_flag",
  "muscle_up",
  "planche",
  "front_lever",
  "back_lever",
  "handstand_push_up",
  "v_sit",
] as const;

export const SKILL_STAGE_COUNTS: Record<string, number> = {
  muscle_up: 5,
  planche: 6,
  front_lever: 6,
  back_lever: 5,
  v_sit: 8,
  handstand_push_up: 5,
  human_flag: 8,
  one_arm_pull_up: 6,
  one_arm_push_up: 8,
  one_arm_handstand: 11,
  dragon_flag: 7,
  shrimp_squat: 5,
  hefesto: 6,
};

export function registerSkillTools(server: McpServer, userId: string) {
  server.tool(
    "update_skill_progress",
    "Upsert progress for a skill (current stage, stage name, percent).",
    updateSkillProgressInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("skill_progressions")
          .upsert(
            {
              user_id: userId,
              skill_name: input.skill_name,
              current_stage: input.current_stage,
              stage_name: input.stage_name,
              progress_percent: input.progress_percent,
              notes: input.notes ?? null,
              last_updated: new Date().toISOString(),
            },
            { onConflict: "skill_name,user_id" }
          )
          .select("*")
          .single();

        if (error) throw error;
        return ok({ skill: data });
      } catch (err) {
        console.error("update_skill_progress failed", { input, err });
        return fail("update_skill_progress", err);
      }
    }
  );

  server.tool(
    "get_skill_overview",
    "Return progress for all 13 tracked skills. Skills with no row appear as stage 0 / 0%.",
    {},
    async () => {
      try {
        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("skill_progressions")
          .select("*")
          .eq("user_id", userId)
          .order("skill_name", { ascending: true });

        if (error) throw error;

        const byName = new Map<string, any>();
        for (const row of data ?? []) byName.set(row.skill_name, row);

        const overview = [...SEED_SKILLS]
          .sort()
          .map((name) => {
            const existing = byName.get(name);
            if (existing) return existing;
            return {
              skill_name: name,
              current_stage: 0,
              stage_name: "not_started",
              progress_percent: 0,
              total_stages: SKILL_STAGE_COUNTS[name] ?? null,
              last_updated: null,
              notes: null,
            };
          });

        return ok({ skills: overview });
      } catch (err) {
        console.error("get_skill_overview failed", { err });
        return fail("get_skill_overview", err);
      }
    }
  );

  server.tool(
    "get_skill_detail",
    "Return current progress and total stage count for a single skill.",
    getSkillDetailInput,
    async (input) => {
      try {
        const supabase = getSupabase();
        const { data, error } = await supabase
          .from("skill_progressions")
          .select("*")
          .eq("skill_name", input.skill_name)
          .eq("user_id", userId)
          .maybeSingle();

        if (error) throw error;

        const total_stages = SKILL_STAGE_COUNTS[input.skill_name] ?? null;

        return ok({
          skill: data ?? {
            skill_name: input.skill_name,
            current_stage: 0,
            stage_name: "not_started",
            progress_percent: 0,
            last_updated: null,
            notes: null,
          },
          total_stages,
        });
      } catch (err) {
        console.error("get_skill_detail failed", { input, err });
        return fail("get_skill_detail", err);
      }
    }
  );
}
