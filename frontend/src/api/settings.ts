import { z } from "zod";
import { requestJson } from "./http";

const gpuSchema = z.object({ value: z.string(), label: z.string() }).passthrough();

export const configSchema = z
  .object({
    gpu: z.string().default(""), default_gpu: z.string().default(""),
    available_gpus: z.array(gpuSchema).default([]), persisted_gpu: z.string().default(""),
    output_format: z.string().default("original"), quality: z.number().default(75),
    webp_lossless_compression: z.string().default("balanced"), auto_save_local: z.boolean().default(false),
    save_folder: z.string().default(""), save_metadata_sidecar: z.boolean().default(true),
    preview_default: z.enum(["off", "on"]).default("off"), preview_codec: z.string().default("webp"),
    preview_quality: z.number().default(70), data_saver_default: z.enum(["off", "on"]).default("off"),
    data_saver_codec: z.string().default("webp"), data_saver_quality: z.number().default(70),
    execution_mode: z.string().default("v2"), execution_mode_source: z.string().default(""),
    execution_mode_locked: z.boolean().default(false), engine_migration_notice: z.string().nullable().default(null),
    skip_plan_validation: z.boolean().default(false), golden_gpu_order: z.record(z.string()).default({}),
  }).passthrough();

export type StudioConfig = z.infer<typeof configSchema>;
export const profileLevelSchema = z.object({ status: z.string().optional(), level: z.string().default("off"), effective: z.string().default("off") }).passthrough();

export async function getConfig(): Promise<StudioConfig> { return configSchema.parse(await requestJson<unknown>("/config")); }
export async function updateConfig(patch: Record<string, unknown>) { return requestJson<{ status: string }>("/config", { method: "POST", body: patch }); }
export async function getProfileLevel() { return profileLevelSchema.parse(await requestJson<unknown>("/profile/level")); }
export async function updateProfileLevel(level: string) { return requestJson<{ status: string }>("/profile/level", { method: "POST", body: { level } }); }
export async function listGoldenProfiles() { return requestJson<unknown>("/studio/golden/profiles"); }
export async function updateGoldenGpuOrder(profile: string, order: string) { return requestJson<{ status: string }>("/studio/golden/gpu-order", { method: "POST", body: { profile, order } }); }
export async function triggerGoldenDeploy(profile: string) { return requestJson<{ status: string }>("/studio/golden/deploy", { method: "POST", body: { profile } }); }
export async function getGoldenDeployStatus(profile: string) { return requestJson<unknown>(`/studio/golden/deploy?profile=${encodeURIComponent(profile)}`); }
