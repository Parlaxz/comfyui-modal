/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}

interface Window {
  _comfyModalOutputOptions?: Record<string, unknown>;
  __comfymodalOpenVueStudio?: (page?: string) => Promise<unknown>;
  __comfymodalCloseVueStudio?: () => void;
}
