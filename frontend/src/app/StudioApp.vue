<script setup lang="ts">
import { computed, onMounted } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import {
  FlaskConical,
  History,
  Layers,
  ServerCog,
  Settings,
  X,
} from "@lucide/vue";
import { STUDIO_PAGES, STUDIO_PAGE_LABELS, type StudioPage } from "./router/studioRoute";
import { useSettingsStore } from "../stores/settings";
import { useInfrastructureStore } from "../stores/infrastructure";
import { cn } from "../components/cn";

const route = useRoute();
const settings = useSettingsStore();
const infrastructure = useInfrastructureStore();

onMounted(() => {
  void settings.initialize();
  void infrastructure.initialize();
});

const NAV_ICONS: Record<StudioPage, unknown> = {
  playground: FlaskConical,
  history: History,
  workflows: Layers,
  backend: ServerCog,
  settings: Settings,
};

const activePage = computed(() => String(route.name ?? "playground"));

function navClass(page: StudioPage): string {
  const active = activePage.value === page;
  return cn(
    "cmst:relative cmst:flex cmst:items-center cmst:gap-1.5 cmst:px-1 cmst:py-2 cmst:text-[13px] cmst:font-medium cmst:no-underline cmst:transition-colors",
    active
      ? "cmst:text-cmst-fg after:cmst:absolute after:cmst:inset-x-0 after:cmst:-bottom-px after:cmst:h-0.5 after:cmst:rounded-full after:cmst:bg-cmst-primary"
      : "cmst:text-cmst-muted cmst:hover:text-cmst-fg",
  );
}

// Integrated close: the host owns overlay lifecycle (Escape + backdrop).
// This affordance asks the host to close without touching its contract —
// both paths are optional, so a standalone preview simply no-ops.
function closeStudio(): void {
  window.dispatchEvent(new CustomEvent("comfymodal:close-vue-studio"));
  const host = window as unknown as {
    __comfymodalCloseVueStudio?: () => void;
  };
  host.__comfymodalCloseVueStudio?.();
}
</script>

<template>
  <!-- Note: no data-studio-app here on purpose. The host mount element
    already carries it (see web/studio-vue-host.js); duplicating it would
    nest the scoping hook. All cmst: utilities and [data-studio-app]
    descendant rules apply through the single host-owned root. -->
  <div
    data-testid="vue-studio-root"
    class="cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:bg-cmst-bg cmst:text-cmst-fg"
  >
    <!-- Right padding reserves room for the host-owned preview close
      (`.comfymodal-vue-studio-close`, 32px at frame top-right): without it
      the host button lands on top of the in-app close. -->
    <header class="cmst:flex cmst:items-center cmst:gap-3 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:py-0 cmst:pl-4 cmst:pr-14">
      <span class="cmst:shrink-0 cmst:py-2.5 cmst:text-[13px] cmst:font-semibold cmst:tracking-tight cmst:text-cmst-fg">
        Modal Studio
      </span>
      <nav aria-label="Studio pages" class="cmst:flex cmst:min-w-0 cmst:flex-1 cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-0">
        <RouterLink
          v-for="page in STUDIO_PAGES"
          :key="page"
          :to="{ name: page }"
          :class="navClass(page)"
          :data-testid="`vue-nav-${page}`"
          :aria-current="activePage === page ? 'page' : undefined"
        >
          <component :is="NAV_ICONS[page]" class="cmst:size-4" aria-hidden="true" />
          {{ STUDIO_PAGE_LABELS[page] }}
        </RouterLink>
      </nav>
      <button
        type="button"
        data-testid="vue-studio-close"
        aria-label="Close Studio"
        class="cmst:shrink-0 cmst:rounded-md cmst:p-1.5 cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg"
        @click="closeStudio"
      >
        <X class="cmst:size-4" aria-hidden="true" />
      </button>
    </header>

    <main class="cmst:flex-1 cmst:min-w-0">
      <RouterView />
    </main>
  </div>
</template>
