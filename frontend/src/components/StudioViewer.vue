<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import type { HistoryRecord } from "../api/history";
import { selectDetailAsset } from "../api/history";
import { useHistoryStore } from "../stores/history";
import StudioButton from "./StudioButton.vue";

const props = defineProps<{ record: HistoryRecord | null }>();
const emit = defineEmits<{ close: [] }>();
const history = useHistoryStore();
const noteDraft = ref(props.record?.note ?? "");
const confirmDelete = ref(false);
const busyAction = ref<string | null>(null);
const closeBtn = ref<HTMLElement | null>(null);
const previousFocus = ref<HTMLElement | null>(null);

onMounted(() => {
  previousFocus.value = document.activeElement as HTMLElement | null;
  noteDraft.value = props.record?.note ?? "";
  closeBtn.value?.focus();
});

onUnmounted(() => {
  previousFocus.value?.focus?.();
});

async function run(action: string, fn: () => Promise<unknown>) {
  busyAction.value = action;
  try {
    await fn();
  } catch {
    // Store error surfaces through detailError/actionMessage.
  } finally {
    busyAction.value = null;
  }
}

function close() {
  emit("close");
}
</script>

<template>
  <div
    v-if="record"
    class="cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6"
    data-state="open"
    data-testid="vue-history-viewer"
    role="dialog"
    aria-modal="true"
    :aria-label="`${record.kind} detail`"
    tabindex="-1"
    @keydown.esc.stop="close"
  >
    <div class="cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2">
        <div>
          <h2 class="cmst:text-lg cmst:font-semibold">{{ record.workflow || record.id }}</h2>
          <p class="cmst:text-xs cmst:opacity-70">{{ record.status }} · {{ record.kind }} · {{ record.id }}</p>
        </div>
        <StudioButton ref="closeBtn" variant="outline" size="sm" data-testid="vue-viewer-close" @click="close">Close</StudioButton>
      </div>

      <div v-if="history.detailError" class="cmst:mt-2 cmst:text-sm cmst:text-red-300" role="alert">{{ history.detailError }}</div>
      <p v-if="history.actionMessage" class="cmst:mt-2 cmst:text-xs cmst:opacity-70" role="status">{{ history.actionMessage }}</p>

      <img
        v-if="record.featuredOutput"
        :src="selectDetailAsset(record.featuredOutput)"
        :alt="record.workflow || record.id"
        class="cmst:mx-auto cmst:mt-4 cmst:max-h-[50vh] cmst:max-w-full cmst:object-contain"
        :data-testid="`vue-viewer-image-${record.id}`"
      />
      <p v-else class="cmst:mt-4 cmst:text-sm cmst:opacity-70">No projected image asset.</p>

      <div v-if="record.errors.length" class="cmst:mt-3 cmst:text-sm cmst:text-red-300">
        <p v-for="(entry, index) in record.errors" :key="index">{{ entry.code }}: {{ entry.message }}</p>
      </div>

      <div class="cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2">
        <div class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">
          <h3 class="cmst:font-semibold">Annotations</h3>
          <div class="cmst:mt-2 cmst:flex cmst:items-center cmst:gap-2">
            <StudioButton size="sm" variant="outline" :aria-pressed="record.favorite ? 'true' : 'false'" :data-testid="`vue-viewer-favorite-${record.id}`" @click="run('favorite', () => history.setFavorite(record!, !record!.favorite))">
              {{ record.favorite ? "★ Favorited" : "☆ Favorite" }}
            </StudioButton>
          </div>
          <label class="cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-xs">
            Note
            <textarea v-model="noteDraft" rows="2" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-sm" :data-testid="`vue-viewer-note-${record.id}`" />
          </label>
          <StudioButton class="cmst:mt-2" size="sm" variant="secondary" :data-testid="`vue-viewer-note-save-${record.id}`" @click="run('note', () => history.setNote(record!, noteDraft))">Save note</StudioButton>
        </div>

        <div v-if="record.kind === 'generation'" class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">
          <h3 class="cmst:font-semibold">Replay</h3>
          <div class="cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2">
            <StudioButton size="sm" variant="outline" :disabled="!record.replayCapable || busyAction !== null" :data-testid="`vue-viewer-original-${record.id}`" @click="run('original', () => history.runReplayAction(record!, 'original'))">Generate Original</StudioButton>
            <StudioButton size="sm" variant="outline" :disabled="!record.replayCapable || busyAction !== null" :data-testid="`vue-viewer-retry-${record.id}`" @click="run('retry', () => history.runReplayAction(record!, 'retry'))">Retry Original</StudioButton>
            <StudioButton size="sm" variant="outline" :disabled="busyAction !== null" :data-testid="`vue-viewer-resume-${record.id}`" @click="run('resume', () => history.runReplayAction(record!, 'resume'))">Resume</StudioButton>
          </div>
          <p v-if="!record.replayCapable" class="cmst:mt-1 cmst:text-xs cmst:opacity-70">{{ record.replayReason || "Not replay-capable." }}</p>
          <h3 class="cmst:mt-3 cmst:font-semibold">Outputs</h3>
          <div v-for="output in record.outputs" :key="output.index" class="cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs">
            <p>{{ output.filename || `output ${output.index}` }} · {{ output.exportState }}</p>
            <div class="cmst:mt-1 cmst:flex cmst:flex-wrap cmst:gap-1">
              <StudioButton size="sm" variant="ghost" :data-testid="`vue-download-${output.assetId}`" @click="run(`download-${output.index}`, () => history.downloadHistoryAsset(record!, output, 'original'))">Download</StudioButton>
              <StudioButton size="sm" variant="ghost" :data-testid="`vue-export-${output.assetId}`" @click="run(`export-${output.index}`, () => history.exportAsset(output))">Export</StudioButton>
              <StudioButton size="sm" variant="ghost" @click="run(`open-${output.index}`, () => history.openHistoryAsset(output.assetId))">Open</StudioButton>
              <StudioButton size="sm" variant="ghost" @click="run(`reveal-${output.index}`, () => history.revealHistoryAsset(output.assetId))">Reveal</StudioButton>
              <StudioButton size="sm" variant="ghost" :data-testid="`vue-featured-${output.index}`" @click="run('featured', () => history.setFeatured(record!, output.index))">Feature</StudioButton>
            </div>
          </div>
        </div>

        <div v-else class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">
          <h3 class="cmst:font-semibold">Experiment</h3>
          <p class="cmst:mt-1 cmst:text-xs cmst:opacity-70">Cells: {{ record.counts.cells }} · Results: {{ record.counts.results }} · Failed: {{ record.counts.failed }}</p>
          <div class="cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2">
            <StudioButton size="sm" variant="outline" :data-testid="`vue-experiment-resume-${record.id}`" @click="run('exp-resume', () => history.runExperimentAction(record!, 'resume'))">Resume</StudioButton>
            <StudioButton size="sm" variant="outline" :data-testid="`vue-experiment-cancel-${record.id}`" @click="run('exp-cancel', () => history.runExperimentAction(record!, 'cancel'))">Cancel</StudioButton>
          </div>
          <div v-for="cell in record.cells" :key="cell.id" class="cmst:mt-2 cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:p-2 cmst:text-xs" :data-testid="`vue-cell-${cell.id}`">
            <p>{{ cell.id }} · {{ cell.status }}</p>
            <StudioButton v-if="cell.status === 'failed'" class="cmst:mt-1" size="sm" variant="ghost" :data-testid="`vue-cell-retry-${cell.id}`" @click="run(`cell-${cell.id}`, () => history.runExperimentAction(record!, 'cancel', cell.id))">Retry cell</StudioButton>
          </div>
        </div>
      </div>

      <div class="cmst:mt-4 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2">
        <div class="cmst:flex cmst:flex-wrap cmst:gap-2">
          <StudioButton size="sm" variant="outline" :data-testid="`vue-compare-set-a-${record.id}`" @click="history.selectCompare('a', record.id)">Compare A</StudioButton>
          <StudioButton size="sm" variant="outline" :data-testid="`vue-compare-set-b-${record.id}`" @click="history.selectCompare('b', record.id)">Compare B</StudioButton>
        </div>
        <div v-if="!confirmDelete">
          <StudioButton size="sm" variant="outline" :data-testid="`vue-delete-${record.id}`" @click="confirmDelete = true">Delete</StudioButton>
        </div>
        <div v-else class="cmst:flex cmst:items-center cmst:gap-2">
          <span class="cmst:text-xs">Delete this {{ record.kind }}?</span>
          <StudioButton size="sm" :data-testid="`vue-delete-confirm-${record.id}`" @click="run('delete', () => history.remove(record!).then(close))">Confirm delete</StudioButton>
          <StudioButton size="sm" variant="ghost" @click="confirmDelete = false">Cancel</StudioButton>
        </div>
      </div>
    </div>
  </div>
</template>
