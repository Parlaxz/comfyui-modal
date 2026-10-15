<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ServerCog, Info } from "@lucide/vue";
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from "reka-ui";
import { useInfrastructureStore } from "../stores/infrastructure";
import { studioButtonClass } from "../components/StudioButton";
import { studioCardClass, studioPageClass } from "../components/studioPanels";

// Phase-1 placeholder: the real Manage-Modal port comes later. This view
// proves the infrastructure store slice and the Studio portal target: the
// Reka Dialog renders into `[data-studio-portals]` (never document.body),
// so overlay styling, z-index, focus, and containment stay inside Studio.

const infra = useInfrastructureStore();
const dialogOpen = ref(false);
const portalTarget = ref<HTMLElement | null>(null);

onMounted(() => {
  portalTarget.value =
    document.querySelector<HTMLElement>("[data-studio-portals]") ?? document.body;
});

function simulateSnapshot() {
  infra.setDeploy("idle", "Phase-1 local snapshot (no backend call).");
  infra.setSyncSummary("sync snapshot: not polled in Phase 1");
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-backend">
    <div :class="studioCardClass('cmst:p-4')">
      <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
        <ServerCog class="cmst:size-5" aria-hidden="true" />
        Manage Modal (Phase-1 proof)
      </h2>
      <p class="cmst:text-sm cmst:opacity-80">
        Route key stays <code>backend</code>. Product functionality is
        intentionally not ported yet.
      </p>
      <div class="cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3">
        <button
          type="button"
          :class="studioButtonClass('secondary', 'sm')"
          @click="simulateSnapshot"
        >
          Simulate local snapshot
        </button>
      </div>
      <p class="cmst:text-sm cmst:mt-2">
        Deploy: <strong>{{ infra.deployState }}</strong>
        <span v-if="infra.deployMessage"> — {{ infra.deployMessage }}</span>
      </p>
    </div>

    <div :class="studioCardClass('cmst:p-4')">
      <h3 class="cmst:text-sm cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
        <Info class="cmst:size-4" aria-hidden="true" />
        Portalled dialog proof (Reka → Studio portal target)
      </h3>
      <DialogRoot v-model:open="dialogOpen">
        <DialogTrigger as-child>
          <button type="button" :class="studioButtonClass('outline', 'sm')" data-testid="vue-dialog-open">
            Open Studio dialog
          </button>
        </DialogTrigger>
        <DialogPortal :to="portalTarget ?? undefined">
          <DialogOverlay class="cmst:fixed cmst:inset-0 cmst:z-[70] cmst:bg-black/60" />
          <DialogContent
            class="cmst:fixed cmst:left-1/2 cmst:top-1/2 cmst:z-[71] cmst:w-[min(28rem,90vw)] cmst:-translate-x-1/2 cmst:-translate-y-1/2 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-5 cmst:text-cmst-fg cmst:shadow-xl"
            data-testid="vue-dialog-content"
          >
            <DialogTitle class="cmst:text-base cmst:font-semibold">
              Contained in [data-studio-portals]
            </DialogTitle>
            <DialogDescription class="cmst:text-sm cmst:opacity-80 cmst:mt-1">
              This overlay teleports into the Studio portal host, not
              document.body. Focus returns to the trigger on close.
            </DialogDescription>
            <div class="cmst:flex cmst:justify-end cmst:mt-4">
              <DialogClose as-child>
                <button
                  type="button"
                  :class="studioButtonClass('default', 'sm')"
                  data-testid="vue-dialog-close"
                >
                  Close
                </button>
              </DialogClose>
            </div>
          </DialogContent>
        </DialogPortal>
      </DialogRoot>
    </div>
  </section>
</template>
