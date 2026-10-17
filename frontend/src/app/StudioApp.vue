<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import {
  FlaskConical,
  History,
  Layers,
  Menu,
  ServerCog,
  Settings,
  X,
} from "@lucide/vue";
import { STUDIO_PAGE_LABELS, type StudioPage } from "./router/studioRoute";
import { useSettingsStore } from "../stores/settings";
import { useInfrastructureStore } from "../stores/infrastructure";
import { useWorkflowsStore } from "../stores/workflows";
import { cn } from "../components/cn";

const route = useRoute();
const settings = useSettingsStore();
const infrastructure = useInfrastructureStore();
const workflows = useWorkflowsStore();
const drawerOpen = ref(false);
const drawerPanel = ref<HTMLElement | null>(null);
const closeBtn = ref<HTMLElement | null>(null);

onMounted(() => {
  void settings.initialize();
  void infrastructure.initialize();
  // The bundle mounted: the Vue topbar owns the single Studio-close
  // affordance, so the host parks its fallback close button (see host CSS).
  // Focus starts on it, matching the previous host-button focus behavior.
  try {
    document.body.setAttribute("data-cmv-vue-ready", "1");
  } catch { /* non-DOM test host */
  }
  closeBtn.value?.focus();
});

const NAV_ICONS: Record<StudioPage, unknown> = {
  playground: FlaskConical,
  history: History,
  workflows: Layers,
  backend: ServerCog,
  settings: Settings,
};

// Drawer groups: Playground + History stay primary; the rest move out of the
// top chrome into the drawer (no top tab strip).
const PRIMARY_PAGES: StudioPage[] = ["playground", "history"];
const SECONDARY_PAGES: StudioPage[] = ["workflows", "backend", "settings"];

const activePage = computed(() => String(route.name ?? "playground"));
const activeLabel = computed(
  () => STUDIO_PAGE_LABELS[(activePage.value as StudioPage) ?? "playground"] ?? "Studio",
);

// Setup mode: while the workflow wizard owns the session, the Studio surface
// collapses to chrome + the setup strip (WorkflowsView hides its editor) so
// the host frame shrinks and the ComfyUI graph becomes the primary surface.
const setupActive = computed(() => workflows.wizardOpen);

function openDrawer(): void {
  drawerOpen.value = true;
}

function closeDrawer(): void {
  drawerOpen.value = false;
}

// Route changes always dismiss the drawer; the drawer never owns routing.
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false;
  },
);

// Opening moves focus into the panel so Escape + screen readers land in the
// drawer instead of the page behind it.
watch(drawerOpen, (open) => {
  if (!open) return;
  void nextTick(() => {
    drawerPanel.value?.focus();
  });
});

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
    class="cmst:relative cmst:flex cmst:flex-col cmst:bg-cmst-bg cmst:text-cmst-fg"
    :class="setupActive ? 'cmst:min-h-0' : 'cmst:min-h-[60vh]'"
  >
    <!-- Right padding reserves room for the host-owned preview close
      (`.comfymodal-vue-studio-close`, 32px at frame top-right): without it
      the host button lands on top of the in-app close. -->
    <header class="cmst:flex cmst:h-14 cmst:items-center cmst:gap-3 cmst:border-b cmst:border-solid cmst:border-cmst-border cmst:pl-3 cmst:pr-14">
      <button
        type="button"
        aria-label="Open navigation"
        data-testid="vue-nav-drawer-open"
        class="cmst:shrink-0 cmst:rounded-md cmst:p-2 cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg"
        @click="openDrawer"
      >
        <Menu class="cmst:size-4" aria-hidden="true" />
      </button>
      <span class="cmst:shrink-0 cmst:text-[13px] cmst:font-semibold cmst:tracking-tight cmst:text-cmst-fg">
        Modal Studio
      </span>
      <span aria-hidden="true" class="cmst:shrink-0 cmst:text-cmst-muted">/</span>
      <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:text-cmst-muted">
        {{ activeLabel }}
      </span>
      <button
        ref="closeBtn"
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

    <!-- Navigation drawer: primary destinations first, then the rest. The
      top chrome carries no tabs; RouterLinks keep the vue-nav-* contract. -->
    <template v-if="drawerOpen">
      <button
        type="button"
        aria-label="Close navigation"
        class="cmst-drawer-backdrop"
        data-testid="vue-nav-drawer-backdrop"
        @click="closeDrawer"
      />
      <div
        ref="drawerPanel"
        class="cmst-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Studio navigation"
        data-testid="vue-nav-drawer"
        tabindex="-1"
        @keydown.esc.stop="closeDrawer"
      >
        <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:px-4 cmst:py-3">
          <span class="cmst:text-[13px] cmst:font-semibold cmst:tracking-tight cmst:text-cmst-fg">
            Modal Studio
          </span>
          <button
            type="button"
            aria-label="Close navigation"
            class="cmst-close-btn"
            @click="closeDrawer"
          >
            <X class="cmst:size-4" aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Studio pages" class="cmst:flex cmst:flex-1 cmst:flex-col cmst:gap-0.5 cmst:overflow-y-auto cmst:px-3 cmst:pb-4">
          <RouterLink
            v-for="page in PRIMARY_PAGES"
            :key="page"
            :to="{ name: page }"
            class="cmst-drawer-row"
            :data-active="activePage === page"
            :data-testid="`vue-nav-${page}`"
            :aria-current="activePage === page ? 'page' : undefined"
          >
            <component :is="NAV_ICONS[page]" class="cmst:size-4" aria-hidden="true" />
            {{ STUDIO_PAGE_LABELS[page] }}
          </RouterLink>
          <p class="cmst-micro cmst:px-3 cmst:pb-1 cmst:pt-4">Studio</p>
          <RouterLink
            v-for="page in SECONDARY_PAGES"
            :key="page"
            :to="{ name: page }"
            class="cmst-drawer-row"
            :data-active="activePage === page"
            :data-testid="`vue-nav-${page}`"
            :aria-current="activePage === page ? 'page' : undefined"
            :class="cn(activePage === page && 'cmst:text-cmst-fg')"
          >
            <component :is="NAV_ICONS[page]" class="cmst:size-4" aria-hidden="true" />
            {{ STUDIO_PAGE_LABELS[page] }}
            <span v-if="page === 'workflows'" class="cmst-drawer-hint">Library + setup</span>
            <span v-else-if="page === 'backend'" class="cmst-drawer-hint">Deployment + models</span>
            <span v-else-if="page === 'settings'" class="cmst-drawer-hint">Preferences</span>
          </RouterLink>
        </nav>
      </div>
    </template>
  </div>
</template>
