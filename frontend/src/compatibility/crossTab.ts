export type InvalidationKind = "settings" | "workspace" | "history" | "workflows";
const CHANNEL = "comfymodal-studio";

/** Coarse invalidation only; receivers refetch server truth. */
export function createCrossTabInvalidation(onInvalidate: (kind: InvalidationKind) => void) {
  if (typeof BroadcastChannel === "undefined") return () => {};
  const channel = new BroadcastChannel(CHANNEL);
  const listener = (event: MessageEvent) => { const kind = event.data?.kind; if (kind === "settings" || kind === "workspace" || kind === "history" || kind === "workflows") onInvalidate(kind); };
  channel.addEventListener("message", listener);
  return () => { channel.removeEventListener("message", listener); channel.close(); };
}
export function publishCrossTabInvalidation(kind: InvalidationKind): void { if (typeof BroadcastChannel === "undefined") return; const channel = new BroadcastChannel(CHANNEL); channel.postMessage({ kind, at: Date.now() }); channel.close(); }
