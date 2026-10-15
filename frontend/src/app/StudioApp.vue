<script setup lang="ts">
import { computed, onMounted } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import {
  FlaskConical,
  History,
  Layers,
  MonitorSmartphone,
  ServerCog,
  Settings,
} from "@lucide/vue";
import { useMediaQuery } from "@vueuse/core";
import { STUDIO_PAGES, STUDIO_PAGE_LABELS, type StudioPage } from "./router/studioRoute";
import { useOperationsStore } from "../stores/operations";
import { useSettingsStore } from "../stores/settings";
import { useInfrastructureStore } from "../stores/infrastructure";
import { cn } from "../components/cn";

const route = useRoute();
const operations = useOperationsStore();
const settings = useSettingsStore();
const infrastructure = useInfrastructureStore();

onMounted(() => {
  void settings.initialize();
  void infrastructure.initialize();
});

// VueUse where it removes manual plumbing: a media query with no
// matchMedia listener lifecycle of our own.
const isWide = useMediaQuery("(min-width: 768px)");

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
    "cmst:flex cmst:items-center cmst:gap-2 cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:no-underline cmst:border cmst:border-solid cmst:border-transparent",
    active
      ? "cmst:bg-cmst-secondary cmst:text-cmst-fg"
      : "cmst:text-cmst-muted cmst:hover:bg-cmst-secondary cmst:hover:text-cmst-fg",
  );
}
</script>

<template>
  <!-- Note: no data-studio-app here on purpose. The host mount element
    already carries it (see web/studio-vue-host.js); duplicating it would
    nest the scoping hook. All cmst: utilities and [data-studio-app]
    descendant rules apply through the single host-owned root. -->
  <div
    data-testid="vue-studio-root"
    class="cmst:flex cmst:min-h-[60vh] cmst:flex-col cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:text-cmst-fg"
  >
    <header class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:p-3">
      <span class="cmst:mr-2 cmst:text-sm cmst:font-semibold cmst:tracking-tight">
        Modal Studio <span class="cmst:font-normal cmst:opacity-70">· Vue proof shell</span>
      </span>
      <nav aria-label="Studio pages" class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1">
        <RouterLink
          v-for="page in STUDIO_PAGES"
          :key="page"
          :to="{ name: page }"
          :class="navClass(page)"
          :data-testid="`vue-nav-${page}`"
        >
          <component :is="NAV_ICONS[page]" class="cmst:size-4" aria-hidden="true" />
          {{ STUDIO_PAGE_LABELS[page] }}
        </RouterLink>
      </nav>
    </header>

    <main class="cmst:flex-1">
      <RouterView />
    </main>

    <footer
      class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-4 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:px-4 cmst:py-2 cmst:text-xs cmst:opacity-90"
      data-testid="vue-status-strip"
    >
      <span>route: <strong data-testid="vue-status-route">{{ activePage }}</strong></span>
      <span>
        operations: <strong data-testid="vue-status-ops">{{ operations.active.length }} active</strong>
        / {{ operations.all.length }} total
      </span>
      <span>
        density: <strong data-testid="vue-status-density">{{ settings.density }}</strong>
      </span>
      <span class="cmst:flex cmst:items-center cmst:gap-1">
        <MonitorSmartphone class="cmst:size-3.5" aria-hidden="true" />
        viewport: <strong>{{ isWide ? "wide" : "narrow" }}</strong> (VueUse media query)
      </span>
    </footer>
  </div>
</template>
