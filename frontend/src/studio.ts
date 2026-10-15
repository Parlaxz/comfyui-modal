// Modal Studio Vue substrate — production entry.
//
// The ComfyUI host (web/studio-vue-host.js) dynamically imports this
// module's `mountStudioPreview`. One Vue app + one Pinia instance per
// host mount; the host keeps it mounted and shows/hides Studio on
// open/close (Pinia/app state survives close/reopen by design).

import { createApp, type App } from "vue";
import { createPinia, type Pinia } from "pinia";
import type { Router } from "vue-router";
import StudioApp from "./app/StudioApp.vue";
import { createStudioRouter } from "./app/router";
import type { StudioWindow } from "./app/router/studioHistory";
import type { StudioPage } from "./app/router/studioRoute";
import "./studio.css";

export interface StudioPreviewHandle {
  app: App;
  router: Router;
  pinia: Pinia;
  unmount: () => void;
}

export interface MountStudioPreviewOptions {
  initialPage?: StudioPage;
  initialFocus?: string | null;
}

export function mountStudioPreview(
  mountEl: HTMLElement,
  options: MountStudioPreviewOptions = {},
): StudioPreviewHandle {
  const pinia = createPinia();
  const router = createStudioRouter({
    win: window as unknown as StudioWindow,
    initial:
      options.initialPage != null
        ? { page: options.initialPage, focus: options.initialFocus ?? null }
        : undefined,
  });
  const app = createApp(StudioApp);
  app.use(pinia);
  app.use(router);
  app.mount(mountEl);
  return {
    app,
    router,
    pinia,
    unmount: () => {
      app.unmount();
    },
  };
}
