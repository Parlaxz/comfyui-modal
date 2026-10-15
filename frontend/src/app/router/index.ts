// Modal Studio Vue substrate — router factory.
//
// Exactly five routes. `backend` remains the route key even though its UI
// label reads "Manage Modal". There is deliberately NO sixth Docs route:
// Help opens the separate docs surface from the host (unchanged).

import {
  createRouter,
  createMemoryHistory,
  type Router,
  type RouterHistory,
} from "vue-router";
import { createStudioHashHistory, type StudioWindow } from "./studioHistory";
import { STUDIO_PAGES, type StudioPage } from "./studioRoute";
import BackendView from "../../pages/BackendView.vue";
import HistoryView from "../../pages/HistoryView.vue";
import PlaygroundView from "../../pages/PlaygroundView.vue";
import SettingsView from "../../pages/SettingsView.vue";
import WorkflowsView from "../../pages/WorkflowsView.vue";

const PAGE_COMPONENTS = {
  playground: PlaygroundView,
  history: HistoryView,
  workflows: WorkflowsView,
  backend: BackendView,
  settings: SettingsView,
} as const;

export interface CreateStudioRouterOptions {
  initial?: { page: unknown; focus?: string | null };
  /** Injectable window for the hash history (tests use a fake). */
  win?: StudioWindow;
  /** When true, use memory history (unit tests, no URL surface). */
  memory?: boolean;
}

export function createStudioRouter(options: CreateStudioRouterOptions = {}): Router {
  let history: RouterHistory;
  if (options.memory || !options.win) {
    history = createMemoryHistory();
  } else {
    history = createStudioHashHistory(options.win, options.initial);
  }
  const router = createRouter({
    history,
    routes: STUDIO_PAGES.map((page: StudioPage) => ({
      path: `/${page}`,
      name: page,
      component: PAGE_COMPONENTS[page],
    })),
  });
  return router;
}
