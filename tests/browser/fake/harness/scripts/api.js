// ComfyUI Modal — Fake `api` stub for the Playwright harness.
//
// Stands in for ComfyUI's ../../scripts/api.js event bus.  The Studio
// frontend consumes it exclusively through `api.addEventListener` /
// `api.removeEventListener` and reads `event.detail` (see
// web/comfymodal-progress.js — every handler either reads `e.detail` or
// calls `onX(e?.detail)`).  Real CustomEvent objects are dispatched so
// `.type`, `.detail`, and `event instanceof Event` all behave natively.
//
// The stub ALSO runs a pump: every 40ms it short-polls
// GET /__comfymodal_test/events?session=<id>&cursor=<n> and dispatches each
// queued {type, detail} from the fake backend.  This is the seam through
// which scenario tracker events (execution_start, modal_status,
// experiment.worker.progress, experiment.event, …) reach the app.
//
// Session resolution order:
//   1. ?session=<id> query parameter on the harness page URL
//   2. localStorage "comfymodal.fake.session" (set via the setter below)
// Tests are encouraged to create a session with page.request first, then
// navigate to /?session=<id>.  The setter is for the rare test that needs
// to switch sessions after load:
//   await page.evaluate((id) => window.__comfymodalFakeSession(id), sid);

const SESSION_KEY = "comfymodal.fake.session";
const POLL_INTERVAL_MS = 40;
const EVENTS_URL = "/__comfymodal_test/events";

function getSessionId() {
  try {
    const qp = new URLSearchParams(window.location.search).get("session");
    if (qp) return qp;
  } catch { /* ignore */ }
  try {
    return window.localStorage.getItem(SESSION_KEY);
  } catch { /* ignore */ }
  return null;
}

function setSessionId(id) {
  try {
    window.localStorage.setItem(SESSION_KEY, String(id));
  } catch { /* ignore */ }
}

const listeners = new Map(); // type → Set<handler>

const api = {
  addEventListener(type, handler) {
    if (typeof handler !== "function") return;
    let set = listeners.get(type);
    if (!set) {
      set = new Set();
      listeners.set(type, set);
    }
    set.add(handler);
  },
  removeEventListener(type, handler) {
    const set = listeners.get(type);
    if (set) set.delete(handler);
  },
  _dispatch(type, detail) {
    let event;
    try {
      event = new CustomEvent(type, { detail: detail === undefined ? {} : detail });
    } catch {
      event = { type, detail: detail === undefined ? {} : detail, target: window, currentTarget: window };
    }
    const set = listeners.get(type);
    if (set) {
      for (const handler of [...set]) {
        try {
          handler(event);
        } catch (err) {
          console.error("[comfymodal-fake-api] listener error for " + type, err);
        }
      }
    }
  },
  // ComfyUI api exposes these too — safe no-ops for the harness.
  getAPIBase() {
    return "/comfymodal";
  },
  fetchApi() {
    return null;
  },
  _dispose() {
    listeners.clear();
  },
};

async function pumpOnce() {
  const sessionId = getSessionId();
  if (!sessionId) return;
  let cursor = 0;
  try {
    cursor = Number(window.localStorage.getItem("comfymodal.fake.cursor") || 0);
  } catch { /* ignore */ }
  try {
    const res = await fetch(`${EVENTS_URL}?session=${encodeURIComponent(sessionId)}&cursor=${cursor}`, { cache: "no-store" });
    if (!res.ok) return;
    const data = await res.json();
    if (!data || !Array.isArray(data.events) || data.events.length === 0) return;
    for (const ev of data.events) {
      api._dispatch(ev.type, ev.detail);
    }
    try {
      window.localStorage.setItem("comfymodal.fake.cursor", String(data.cursor || 0));
    } catch { /* ignore */ }
  } catch { /* transient — retry next tick */ }
}

function startPump() {
  setInterval(() => {
    pumpOnce().catch(() => {});
  }, POLL_INTERVAL_MS);
}

// Wire up globals and exports.
window.api = api;
window.__comfymodalFakeApi = api;
window.__comfymodalFakeSession = setSessionId;
window.__comfymodalFakeGetSession = getSessionId;

startPump();

export { api };
