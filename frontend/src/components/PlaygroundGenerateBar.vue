<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { ChevronDown, FlaskConical, ListPlus, Play } from "@lucide/vue";

export type GenerateIntent = "generate" | "queue" | "experiment";

const props = defineProps<{
  disabled: boolean;
  reason: string | null;
  busy: boolean;
  busyLabel?: string;
  queueCount: number;
  experimentMode: boolean;
  queueMode: boolean;
}>();

const emit = defineEmits<{
  submit: [intent: GenerateIntent];
}>();

const menuOpen = ref(false);

const primaryLabel = computed(() => {
  if (props.busy) return props.busyLabel ?? "Running…";
  if (props.experimentMode) return "Run experiment";
  if (props.queueMode) return props.queueCount > 0 ? `Queue (${props.queueCount})` : "Queue";
  return "Generate";
});

function choose(intent: GenerateIntent): void {
  menuOpen.value = false;
  emit("submit", intent);
}

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape") menuOpen.value = false;
  if ((event.key === "ArrowDown" || event.key === "Enter") && document.activeElement?.getAttribute("data-testid") === "vue-generate-menu-button") {
    menuOpen.value = true;
  }
}

window.addEventListener("keydown", onKey);
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="cmst:flex cmst:flex-col cmst:gap-1" data-testid="vue-generate-bar">
    <div class="cmst:flex cmst:items-stretch cmst:justify-center">
      <div
        class="cmst:flex cmst:overflow-hidden cmst:rounded-full cmst:bg-gradient-to-r cmst:from-cmst-primary cmst:to-[#7a5cff] cmst:p-[1.5px]"
      >
        <button
          type="button"
          :disabled="disabled"
          class="cmst:flex cmst:h-11 cmst:min-w-52 cmst:items-center cmst:justify-center cmst:gap-2 cmst:rounded-l-full cmst:bg-cmst-primary cmst:px-6 cmst:text-[15px] cmst:font-semibold cmst:text-white cmst:hover:bg-cmst-primary-hover cmst:disabled:cursor-not-allowed cmst:disabled:opacity-50"
          data-testid="vue-generate-submit"
          :aria-label="primaryLabel"
          @click="choose(experimentMode ? 'experiment' : queueMode ? 'queue' : 'generate')"
        >
          <FlaskConical v-if="experimentMode" class="cmst:size-4" aria-hidden="true" />
          <ListPlus v-else-if="queueMode" class="cmst:size-4" aria-hidden="true" />
          <Play v-else class="cmst:size-4" aria-hidden="true" />
          {{ primaryLabel }}
        </button>
        <button
          type="button"
          :disabled="disabled && !menuOpen"
          class="cmst:flex cmst:h-11 cmst:w-11 cmst:items-center cmst:justify-center cmst:rounded-r-full cmst:bg-cmst-primary cmst:text-white cmst:hover:bg-cmst-primary-hover"
          data-testid="vue-generate-menu-button"
          aria-label="More generation options"
          aria-haspopup="menu"
          :aria-expanded="menuOpen ? 'true' : 'false'"
          @click="menuOpen = !menuOpen"
        >
          <ChevronDown class="cmst:size-4" aria-hidden="true" />
        </button>
      </div>
    </div>
    <div
      v-if="menuOpen"
      class="cmst:flex cmst:justify-center"
      role="menu"
      aria-label="Generation intent"
      data-testid="vue-generate-menu"
    >
      <div
        class="cmst:flex cmst:flex-col cmst:gap-0.5 cmst:rounded-xl cmst:bg-cmst-raised cmst:p-1.5 cmst:shadow-xl"
      >
        <button
          type="button"
          role="menuitem"
          class="cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover"
          data-testid="vue-generate-intent-generate"
          @click="choose('generate')"
        >
          Generate — run now
        </button>
        <button
          type="button"
          role="menuitem"
          class="cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover"
          data-testid="vue-generate-intent-queue"
          @click="choose('queue')"
        >
          Queue — collect, then drain as a batch
        </button>
        <button
          type="button"
          role="menuitem"
          class="cmst:rounded-lg cmst:px-4 cmst:py-2 cmst:text-left cmst:text-sm cmst:hover:bg-cmst-hover"
          data-testid="vue-generate-intent-experiment"
          @click="choose('experiment')"
        >
          Experiment — sweep parameter axes
        </button>
      </div>
    </div>
    <p
      v-if="reason"
      class="cmst:text-center cmst:text-[13px] cmst:text-cmst-muted"
      data-testid="vue-generate-gate-reason"
    >
      {{ reason }}
    </p>
  </div>
</template>
