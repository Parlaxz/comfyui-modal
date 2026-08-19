// ComfyUI Modal — Harness bootstrap (test-only).
//
// Loads the fake ComfyUI api/app stubs, ensures Studio styles, mounts the
// real Studio shell into #comfymodal-test-host against the fake backend,
// and exposes control handles for Playwright tests:
//
//   window.__mountStudioForTest()   → Promise<shellApi> (mounts the Studio)
//   window.__studioApi              → the shell api returned by mount
//   window.__comfymodalFakeApi      → the fake ComfyUI api stub (from api.js)
//   window.__comfymodalFakeSession  → (id) setter for the session id
//
// Session mechanics: the fake backend is session-scoped.  The harness reads
// the session id from the page URL (?session=<id>) or localStorage
// ("comfymodal.fake.session") and publishes it as cookie
// `comfymodal_fake_session` so every same-origin /comfymodal fetch the app
// makes automatically targets the right session.  Tests should create a
// session first via POST /__comfymodal_test/session (page.request), then
// navigate to /?session=<id>.

(function init() {
  // Resolve the session id exactly like the api stub pump does.
  let sessionId = null;
  try {
    const qp = new URLSearchParams(window.location.search).get("session");
    if (qp) sessionId = qp;
  } catch { /* ignore */ }
  if (!sessionId) {
    try {
      sessionId = window.localStorage.getItem("comfymodal.fake.session");
    } catch { /* ignore */ }
  }
  if (sessionId) {
    try {
      document.cookie = "comfymodal_fake_session=" + encodeURIComponent(sessionId) + "; path=/; SameSite=Lax";
    } catch { /* ignore */ }
  }
})();

window.__mountStudioForTest = async function mountStudioForTest() {
  // 1. Fake ComfyUI api stub (also starts the event pump + window.api).
  await import("/scripts/api.js");

  // 2. Studio styles.
  const { ensureStudioStyles } = await import("/extensions/comfymodal-modal/studio-styles.js");
  ensureStudioStyles();

  // 3. Mount the real Studio shell against the fake backend.
  const { mountStudioShell } = await import("/extensions/comfymodal-modal/studio-shell.js");
  const host = document.getElementById("comfymodal-test-host");
  const shellApi = mountStudioShell(host, {
    apiBase: "/comfymodal",
    comfyApi: window.api,
    mountLegacyTab: () => {},
    setPage: () => {},
  });
  window.__studioApi = shellApi;
  return shellApi;
};

export {};
