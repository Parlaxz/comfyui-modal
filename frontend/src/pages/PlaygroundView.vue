<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ImagePlus, RotateCcw } from "@lucide/vue";
import { usePlaygroundStore, PLAYGROUND_SUBTOOLS, PLAYGROUND_PLACEHOLDERS } from "../stores/playground";
import { useWorkflowsStore } from "../stores/workflows";
import { useHistoryStore } from "../stores/history";
import { useSettingsStore } from "../stores/settings";
import { selectFeedAsset, type HistoryRecord } from "../api/history";
import StudioButton from "../components/StudioButton.vue";
import HistoryPicker from "../components/HistoryPicker.vue";
import PlaygroundControls from "../components/PlaygroundControls.vue";
import PlaygroundGenerateBar, { type GenerateIntent } from "../components/PlaygroundGenerateBar.vue";
import { studioPageClass } from "../components/studioPanels";

const playground = usePlaygroundStore();
const workflows = useWorkflowsStore();
const history = useHistoryStore();
const settings = useSettingsStore();
const router = useRouter();

const pickerOpen = ref(false);
const pickerRole = ref("source_image");
const composerOpen = ref(false);
const axisInput = ref<Record<string, string>>({});
// Sketch overlay strokes are local-only; a base change clears them.
const sketchStrokes = ref<string[]>([]);

const subtools = computed(() => PLAYGROUND_SUBTOOLS[playground.activeMode]);

const promptRole = computed(() => {
  if (playground.schema.prompt) return "prompt";
  return Object.keys(playground.schema).find((role) => role.endsWith("_prompt")) ?? null;
});

const centerPromptRoles = computed(() => {
  if (playground.activeSubtool !== "text" || !promptRole.value) return [];
  return [promptRole.value, "negative_prompt"].filter((role) => playground.schema[role]);
});

const resultRecord = computed(() =>
  playground.currentGenerationId
    ? (history.records.find((item) => item.id === playground.currentGenerationId) ?? null)
    : null,
);

const resultAsset = computed(() => {
  const record = resultRecord.value;
  const output = record?.featuredOutput;
  if (!output) return null;
  try {
    return selectFeedAsset(output);
  } catch {
    return null;
  }
});

const sourcePreview = computed(() => {
  const value = playground.controlValues.source_image;
  return typeof value === "string" && value ? value : null;
});

function modalOptions(): Record<string, unknown> {
  return {
    ...(settings.outputPreferences ?? {}),
    ...playground.outputOverride,
  };
}

async function refreshWorkflows(): Promise<void> {
  await workflows.initialize();
  const persisted = playground.workflowId;
  const known = workflows.workflows.find((item) => item.workflow_id === persisted);
  const target = known ?? workflows.workflows[0];
  if (target) await chooseWorkflow(String(target.workflow_id));
}

async function chooseWorkflow(id: string): Promise<void> {
  try {
    await workflows.selectWorkflow(id);
  } catch {
    /* detail load is best-effort; run-context is authoritative for Playground */
  }
  const latest =
    workflows.versions.find(
      (item) => item.workflow_version_id === workflows.selectedWorkflow?.latest_version_id,
    ) ??
    workflows.versions[workflows.versions.length - 1] ??
    null;
  await playground.selectWorkflow(id, latest?.workflow_version_id ?? "");
  sketchStrokes.value = [];
}

async function chooseVersion(id: string): Promise<void> {
  try {
    await workflows.selectVersion(id);
  } catch {
    /* same best-effort rule as workflow selection */
  }
  await playground.selectWorkflow(playground.workflowId, id);
  sketchStrokes.value = [];
}

function choosePreset(id: string): void {
  const record = (workflows.presets as Array<Record<string, unknown>>).find(
    (item) => String(item.preset_id ?? item.id) === id,
  );
  const state = (record?.state as Record<string, unknown> | undefined) ?? null;
  playground.applyPreset(state, id);
}

async function onSubmit(intent: GenerateIntent): Promise<void> {
  if (intent === "generate") {
    const result = await playground.submitRun({ modalOptions: modalOptions() });
    if (result.ok) await history.loadFeed();
    return;
  }
  if (intent === "queue") {
    playground.setQueueMode(true);
    playground.enqueueCurrent();
    return;
  }
  playground.setExperimentMode(true);
  composerOpen.value = true;
}

async function drain(): Promise<void> {
  const result = await playground.drainQueue({ modalOptions: modalOptions() });
  if (result.ok) await history.loadFeed();
}

async function submitComposer(): Promise<void> {
  const result = await playground.submitExperimentDef({ modalOptions: modalOptions() });
  if (result.ok) {
    composerOpen.value = false;
    await history.loadFeed();
  }
}

function openPicker(role: string): void {
  pickerRole.value = role;
  pickerOpen.value = true;
}

function usePicked(record: HistoryRecord): void {
  const role = pickerRole.value;
  pickerOpen.value = false;
  const output = record.featuredOutput;
  const url = output ? selectFeedAsset(output) : record.id;
  if (role === "source_image") {
    playground.setSource(String(url), playground.contextKey);
    sketchStrokes.value = [];
  } else {
    playground.addReference(String(url));
  }
}

function toggleAxis(role: string, enabled: boolean): void {
  playground.setAxis(role, { enabled });
}

function axisValues(role: string): string {
  return axisInput.value[role] ?? "";
}

function commitAxisValues(role: string, raw: string): void {
  axisInput.value = { ...axisInput.value, [role]: raw };
  const values = raw
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter((part) => part !== "");
  playground.setAxis(role, { enabled: true, values });
}

function openInHistory(): void {
  if (playground.currentGenerationId) {
    void router.push({ name: "history", query: { focus: playground.currentGenerationId } });
  } else {
    void router.push({ name: "history" });
  }
}

onMounted(async () => {
  await settings.initialize().catch(() => undefined);
  await history.initialize().catch(() => undefined);
  await refreshWorkflows();
});

watch(
  () => playground.controlValues.source_image,
  () => {
    sketchStrokes.value = [];
  },
);
</script>

<template>
  <section :class="studioPageClass('cmst:h-full')" data-testid="vue-page-playground">
    <h2 class="cmst:sr-only" data-testid="vue-playground-title">Playground</h2>

    <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2" data-testid="vue-playground-topbar">
      <select
        id="pg-workflow"
        :value="playground.workflowId"
        class="cmst:h-9 cmst:max-w-64 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"
        aria-label="Workflow"
        data-testid="vue-playground-workflow"
        @change="chooseWorkflow(($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>Select a workflow…</option>
        <option
          v-for="item in workflows.workflows"
          :key="String(item.workflow_id)"
          :value="String(item.workflow_id)"
        >
          {{ String(item.name || item.workflow_id) }}
        </option>
      </select>
      <select
        v-if="workflows.versions.length"
        id="pg-version"
        :value="playground.versionId"
        class="cmst:h-9 cmst:max-w-44 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"
        aria-label="Version"
        data-testid="vue-playground-version"
        @change="chooseVersion(($event.target as HTMLSelectElement).value)"
      >
        <option
          v-for="item in workflows.versions"
          :key="String(item.workflow_version_id)"
          :value="String(item.workflow_version_id)"
        >
          v{{ String(item.version ?? item.workflow_version_id).slice(0, 8) }}
        </option>
      </select>
      <select
        v-if="(workflows.presets as unknown[]).length"
        id="pg-preset"
        :value="playground.presetId ?? ''"
        class="cmst:h-9 cmst:max-w-44 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"
        aria-label="Preset"
        data-testid="vue-playground-preset"
        @change="choosePreset(($event.target as HTMLSelectElement).value)"
      >
        <option value="">No preset</option>
        <option
          v-for="item in (workflows.presets as Array<Record<string, unknown>>)"
          :key="String(item.preset_id ?? item.id)"
          :value="String(item.preset_id ?? item.id)"
        >
          {{ String(item.name ?? item.preset_id ?? item.id) }}
        </option>
      </select>
      <span v-if="playground.presetDirty" class="cmst:text-xs cmst:text-cmst-muted" data-testid="vue-playground-preset-dirty">
        Modified
      </span>
      <div class="cmst:ml-auto cmst:flex cmst:items-center cmst:gap-1" role="tablist" aria-label="Tool">
        <button
          v-for="mode in (['generate', 'edit', 'post'] as const)"
          :key="mode"
          type="button"
          role="tab"
          :aria-selected="playground.activeMode === mode ? 'true' : 'false'"
          class="cmst:rounded-lg cmst:px-2.5 cmst:py-1.5 cmst:text-[13px] cmst:capitalize"
          :class="playground.activeMode === mode ? 'cmst:bg-cmst-raised cmst:text-cmst-fg' : 'cmst:text-cmst-muted cmst:hover:bg-cmst-hover'"
          :data-testid="`vue-playground-mode-${mode}`"
          @click="playground.setTool(mode, PLAYGROUND_SUBTOOLS[mode][0])"
        >
          {{ mode }}
        </button>
      </div>
    </div>

    <div class="cmst:flex cmst:flex-wrap cmst:gap-1" role="tablist" aria-label="Subtool" data-testid="vue-playground-subtools">
      <button
        v-for="sub in subtools"
        :key="sub"
        type="button"
        role="tab"
        :aria-selected="playground.activeSubtool === sub ? 'true' : 'false'"
        :disabled="PLAYGROUND_PLACEHOLDERS.includes(sub)"
        :title="PLAYGROUND_PLACEHOLDERS.includes(sub) ? 'Arrives in a later phase — execution is disabled' : ''"
        class="cmst:rounded-lg cmst:px-2.5 cmst:py-1.5 cmst:text-[13px] cmst:capitalize cmst:disabled:cursor-not-allowed cmst:disabled:opacity-40"
        :class="playground.activeSubtool === sub ? 'cmst:bg-cmst-raised cmst:text-cmst-fg' : 'cmst:text-cmst-muted cmst:hover:bg-cmst-hover'"
        :data-testid="`vue-playground-subtool-${sub}`"
        @click="playground.setTool(playground.activeMode, sub)"
      >
        {{ sub }}
      </button>
    </div>

    <div class="cmst:grid cmst:flex-1 cmst:grid-cols-1 cmst:gap-4 cmst:lg:grid-cols-[minmax(0,1fr)_320px]">
      <div class="cmst:flex cmst:min-w-0 cmst:flex-col cmst:gap-3" data-testid="vue-playground-workspace">
        <div
          class="cmst:flex cmst:min-h-64 cmst:flex-1 cmst:items-center cmst:justify-center cmst:overflow-hidden cmst:rounded-xl cmst:bg-cmst-matte"
          data-testid="vue-playground-canvas"
        >
          <img
            v-if="resultAsset"
            :src="resultAsset"
            alt="Current generation result"
            class="cmst:max-h-[52vh] cmst:w-full cmst:object-contain"
            data-testid="vue-playground-result"
          />
          <div
            v-else-if="sourcePreview"
            class="cmst:flex cmst:flex-col cmst:items-center cmst:gap-2 cmst:p-4"
          >
            <img
              :src="sourcePreview"
              alt="Source image"
              class="cmst:max-h-[44vh] cmst:rounded cmst:object-contain"
              data-testid="vue-playground-source-preview"
            />
            <span class="cmst:text-xs cmst:text-cmst-muted">Source image</span>
          </div>
          <div v-else class="cmst:flex cmst:flex-col cmst:items-center cmst:gap-2 cmst:p-8 cmst:text-center">
            <ImagePlus class="cmst:size-6 cmst:opacity-40" aria-hidden="true" />
            <p class="cmst:max-w-80 cmst:text-sm cmst:text-cmst-muted">
              {{
                playground.contextStatus === "loading"
                  ? "Loading workflow…"
                  : playground.workflowId
                    ? "No output yet. Describe the image, then Generate."
                    : "Select a workflow to begin."
              }}
            </p>
          </div>
        </div>

        <div
          v-if="playground.runState.message"
          class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]"
          data-testid="vue-playground-run-status"
          role="status"
        >
          <span class="cmst:text-cmst-secondary-text">{{ playground.runState.message }}</span>
          <button
            v-if="playground.isBusy"
            type="button"
            class="cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover"
            data-testid="vue-playground-cancel"
            @click="playground.cancelRun()"
          >
            Cancel
          </button>
          <button
            v-if="playground.currentGenerationId && playground.runState.status === 'succeeded'"
            type="button"
            class="cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover"
            data-testid="vue-playground-open-history"
            @click="openInHistory"
          >
            Open in History
          </button>
        </div>

        <div v-if="centerPromptRoles.length" class="cmst:flex cmst:flex-col cmst:gap-2" data-testid="vue-playground-prompt-zone">
          <div v-for="role in centerPromptRoles" :key="role" class="cmst:flex cmst:flex-col cmst:gap-1.5">
            <label :for="`pg-center-${role}`" class="cmst:text-[13px] cmst:font-medium cmst:text-cmst-secondary-text">
              {{ role === "prompt" ? "Prompt" : "Negative prompt" }}
            </label>
            <textarea
              :id="`pg-center-${role}`"
              :value="String(playground.controlValues[role] ?? '')"
              :rows="role === 'prompt' ? 4 : 2"
              class="cmst:w-full cmst:rounded-xl cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-3 cmst:py-2.5 cmst:text-[15px]"
              :data-testid="`vue-playground-prompt-${role}`"
              @input="playground.setControl(role, ($event.target as HTMLTextAreaElement).value)"
            />
          </div>
        </div>

        <div v-if="playground.activeSubtool === 'references'" class="cmst:flex cmst:flex-col cmst:gap-2" data-testid="vue-playground-references">
          <div class="cmst:flex cmst:items-center cmst:justify-between">
            <h3 class="cmst:text-sm cmst:font-semibold">References</h3>
            <StudioButton variant="ghost" size="sm" data-testid="vue-playground-add-reference" @click="openPicker('references')">
              Add from History
            </StudioButton>
          </div>
          <p v-if="!playground.references.length" class="cmst:text-[13px] cmst:text-cmst-muted">
            No reference images. They ride alongside the run without entering control values.
          </p>
          <ul v-else class="cmst:flex cmst:flex-col cmst:gap-1.5">
            <li
              v-for="item in playground.references"
              :key="item.id"
              class="cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-lg cmst:bg-cmst-surface cmst:px-2.5 cmst:py-2 cmst:text-[13px]"
              :data-testid="`vue-playground-reference-${item.id}`"
            >
              <img :src="item.filename" :alt="item.filename" class="cmst:size-10 cmst:rounded cmst:object-cover" loading="lazy" />
              <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate">{{ item.filename }}</span>
              <button
                type="button"
                class="cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:hover:bg-cmst-hover"
                :aria-label="`Remove ${item.filename}`"
                @click="playground.removeReference(item.id)"
              >
                Remove
              </button>
            </li>
          </ul>
        </div>

        <div v-if="playground.activeSubtool === 'sketch'" class="cmst:flex cmst:flex-col cmst:gap-2" data-testid="vue-playground-sketch">
          <h3 class="cmst:text-sm cmst:font-semibold">Sketch base</h3>
          <p class="cmst:text-[13px] cmst:text-cmst-muted">
            Changing the base clears overlay strokes. The flattened sketch commits to the source image on save.
          </p>
          <div class="cmst:flex cmst:items-center cmst:gap-2">
            <StudioButton variant="outline" size="sm" data-testid="vue-playground-sketch-history" @click="openPicker('source_image')">
              Use History image as base
            </StudioButton>
            <span v-if="sourcePreview" class="cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]">
              {{ sourcePreview }}
            </span>
            <span v-if="sketchStrokes.length" class="cmst:text-xs cmst:text-cmst-muted">
              {{ sketchStrokes.length }} strokes
            </span>
          </div>
        </div>

        <div
          v-if="playground.queueMode && playground.queueCount > 0"
          class="cmst:flex cmst:flex-col cmst:gap-1.5"
          data-testid="vue-playground-queue"
        >
          <h3 class="cmst:text-sm cmst:font-semibold">Queue ({{ playground.queueCount }})</h3>
          <ul class="cmst:flex cmst:flex-col cmst:gap-1">
            <li
              v-for="item in playground.queue"
              :key="item.id"
              class="cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-lg cmst:bg-cmst-surface cmst:px-2.5 cmst:py-1.5 cmst:text-[13px]"
              :data-testid="`vue-playground-queued-${item.id}`"
            >
              <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate">{{ item.label }}</span>
              <button
                type="button"
                class="cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:hover:bg-cmst-hover"
                :aria-label="`Remove ${item.label}`"
                @click="playground.removeQueued(item.id)"
              >
                Remove
              </button>
            </li>
          </ul>
          <div class="cmst:flex cmst:gap-2">
            <StudioButton variant="default" size="sm" data-testid="vue-playground-drain" @click="drain">
              Drain queue
            </StudioButton>
            <StudioButton variant="ghost" size="sm" data-testid="vue-playground-clear-queue" @click="playground.clearQueue()">
              Clear
            </StudioButton>
          </div>
        </div>
      </div>

      <aside class="cmst:min-w-0 cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4" data-testid="vue-playground-inspector" aria-label="Workflow controls">
        <div v-if="playground.contextStatus === 'loading'" role="status" class="cmst:py-4 cmst:text-sm cmst:opacity-70">
          Loading workflow…
        </div>
        <div v-else-if="playground.contextStatus === 'error'" class="cmst:flex cmst:flex-col cmst:gap-2 cmst:py-4" role="alert">
          <p class="cmst:text-sm">{{ playground.contextError || "Workflow unavailable" }}</p>
          <StudioButton variant="outline" size="sm" @click="refreshWorkflows">
            <RotateCcw class="cmst:size-4" aria-hidden="true" />
            Retry
          </StudioButton>
        </div>
        <PlaygroundControls
          v-else
          :schema="playground.schema"
          :values="playground.controlValues"
          :hide-roles="centerPromptRoles"
          @update="(role, value) => playground.setControl(role, value)"
          @pick-image="openPicker"
          @upload-image="(_role, file) => { void playground.uploadSource(file); }"
          @clear-image="() => playground.clearSource()"
        />
        <div v-if="playground.sourceUploading" class="cmst:py-1 cmst:text-[13px] cmst:opacity-70" role="status">
          Uploading…
        </div>
        <div v-if="playground.sourceError" class="cmst:py-1 cmst:text-[13px]" role="alert">
          {{ playground.sourceError }}
        </div>
      </aside>
    </div>

    <div v-if="composerOpen" class="cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4" data-testid="vue-playground-composer" role="dialog" aria-label="Experiment composer">
      <div class="cmst:flex cmst:items-center cmst:justify-between">
        <h3 class="cmst:text-sm cmst:font-semibold">Experiment axes</h3>
        <div class="cmst:flex cmst:gap-2">
          <StudioButton variant="ghost" size="sm" data-testid="vue-playground-composer-close" @click="composerOpen = false">
            Close
          </StudioButton>
          <StudioButton variant="default" size="sm" data-testid="vue-playground-composer-submit" @click="submitComposer">
            Submit experiment
          </StudioButton>
        </div>
      </div>
      <p class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">
        One value per line or comma-separated. The experiment entity itself lives in History once submitted.
      </p>
      <div class="cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-2">
        <div v-for="role in Object.keys(playground.schema)" :key="role" class="cmst:flex cmst:flex-col cmst:gap-1">
          <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]">
            <input
              :id="`pg-axis-${role}`"
              type="checkbox"
              :checked="Boolean(playground.experimentAxes[role]?.enabled)"
              :data-testid="`vue-playground-axis-${role}`"
              @change="toggleAxis(role, ($event.target as HTMLInputElement).checked)"
            />
            {{ role }}
          </label>
          <textarea
            v-if="playground.experimentAxes[role]?.enabled"
            :id="`pg-axis-values-${role}`"
            :value="axisValues(role)"
            rows="2"
            class="cmst:w-full cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:py-1.5 cmst:text-sm"
            :data-testid="`vue-playground-axis-values-${role}`"
            placeholder="one value per line"
            @input="commitAxisValues(role, ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
      </div>
    </div>

    <footer class="cmst:bg-cmst-bg cmst:py-3" data-testid="vue-playground-action-zone">
      <PlaygroundGenerateBar
        :disabled="playground.gateReason !== null"
        :reason="playground.gateReason"
        :busy="playground.isBusy"
        :busy-label="playground.runState.status === 'submitting' ? 'Submitting…' : 'Running…'"
        :queue-count="playground.queueCount"
        :experiment-mode="playground.experimentMode"
        :queue-mode="playground.queueMode"
        @submit="onSubmit"
      />
    </footer>

    <HistoryPicker
      v-if="pickerOpen"
      @select="usePicked"
      @cancel="pickerOpen = false"
    />
  </section>
</template>
