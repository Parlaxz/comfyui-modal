// ComfyUI-Manager integration (root-relative routes, NOT under /comfymodal).
//
// Mirrors the semantics of web/studio-backend-api.js manager helpers plus
// the pack-resolution/install engine of web/studio-model-library.js:
// identified Manager packs install through the CNR queue (queue + start),
// truly unmatched packs keep the security-gated git_url fallback, and
// nothing here ever reboots or guesses a URL.

export interface ManagerFetchResult {
  ok: boolean;
  status: number;
  data: unknown;
}

async function managerFetch(path: string, options?: RequestInit): Promise<ManagerFetchResult | null> {
  try {
    const response = await fetch(path, options);
    let text = "";
    try {
      text = await response.text();
    } catch {
      text = "";
    }
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { message: text };
      }
    }
    return { ok: response.ok, status: response.status, data };
  } catch {
    return null;
  }
}

export async function getManagerVersion() {
  return managerFetch("/manager/version");
}

export async function managerInstallNode(url: string) {
  return managerFetch("/customnode/install/git_url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export async function managerQueueInstall(packRecord: Record<string, unknown>) {
  return managerFetch("/manager/queue/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(packRecord || {}),
  });
}

export async function managerQueueStart() {
  return managerFetch("/manager/queue/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export async function listManagerInstalled() {
  return managerFetch("/customnode/installed");
}

export async function getManagerModels() {
  const fresh = await managerFetch("/externalmodel/getlist?mode=default");
  if (fresh && fresh.ok) return fresh;
  return managerFetch("/externalmodel/getlist?mode=cache");
}

export async function getManagerPackList() {
  return managerFetch("/customnode/getlist?mode=default&skip_update=true");
}

export async function getManagerMappings() {
  return managerFetch("/customnode/getmappings?mode=default");
}

export interface ManagerPackRecord {
  key: string;
  name: string;
  cnrId: string;
  repository: string;
  version: string;
  selected_version: string;
  channel: string;
  mode: string;
  install_type: string;
  files: string[];
}

function repoSlug(value: string): string {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function basename(value: string): string {
  return String(value || "").split("/").filter(Boolean).pop() || "";
}

function safeRegExp(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern);
  } catch {
    return null;
  }
}

/** Build the Manager pack index (packs/byClass/preemptions/patterns). */
export function buildManagerPackIndex(
  rawPacks: Record<string, Record<string, unknown>>,
  mappings: Record<string, unknown>,
): {
  packs: Record<string, ManagerPackRecord>;
  byClass: Record<string, ManagerPackRecord>;
  preemptions: Record<string, ManagerPackRecord>;
  patterns: Array<{ re: RegExp; record: ManagerPackRecord }>;
} {
  const packs: Record<string, ManagerPackRecord> = {};
  const byClass: Record<string, ManagerPackRecord> = {};
  const preemptions: Record<string, ManagerPackRecord> = {};
  const patterns: Array<{ re: RegExp; record: ManagerPackRecord }> = [];
  const indexByKey = (
    table: Record<string, ManagerPackRecord>,
    key: unknown,
    record: ManagerPackRecord,
  ) => {
    const normalized = String(key == null ? "" : key).toLowerCase();
    if (normalized && !table[normalized]) table[normalized] = record;
  };
  const registerPack = (key: string, raw: Record<string, unknown>) => {
    const record: ManagerPackRecord = {
      key: String(key),
      name: String(raw.title || raw.name || key),
      cnrId: String(raw.cnr_id || (raw.id as string) || key),
      repository: String(raw.repository || ""),
      version: String(raw.version || "unknown"),
      selected_version: String(raw.selected_version || "latest"),
      channel: String(raw.channel || "default"),
      mode: String(raw.mode || "default"),
      install_type: String(raw.install_type || ""),
      files: Array.isArray(raw.files) ? (raw.files as string[]) : [],
    };
    packs[String(key).toLowerCase()] = record;
    const repo = String(raw.repository || "");
    if (repo) {
      indexByKey(packs as unknown as Record<string, ManagerPackRecord>, repoSlug(repo), record);
      indexByKey(packs as unknown as Record<string, ManagerPackRecord>, basename(repo).toLowerCase(), record);
    }
    return record;
  };
  for (const [key, raw] of Object.entries(rawPacks || {})) {
    if (raw && typeof raw === "object") registerPack(key, raw);
  }
  if (mappings && typeof mappings === "object") {
    for (const [key, entry] of Object.entries(mappings)) {
      const classes = Array.isArray(entry) ? entry[0] : (entry as Record<string, unknown>).classes;
      const meta = (Array.isArray(entry) ? entry[1] : {}) as Record<string, unknown>;
      const record =
        packs[String(key).toLowerCase()] || packs[repoSlug(key)];
      if (record) {
        if (Array.isArray(meta.preemptions)) {
          for (const cls of meta.preemptions as string[]) indexByKey(preemptions, cls, record);
        }
        if (typeof meta.nodename_pattern === "string") {
          const re = safeRegExp(meta.nodename_pattern);
          if (re) patterns.push({ re, record });
        }
      }
      for (const cls of Array.isArray(classes) ? (classes as string[]) : []) {
        if (record) indexByKey(byClass, cls, record);
      }
    }
  }
  return { packs, byClass, preemptions, patterns };
}

export interface ManagerPackIndex {
  packs: Record<string, ManagerPackRecord>;
  byClass: Record<string, ManagerPackRecord>;
  preemptions: Record<string, ManagerPackRecord>;
  patterns: Array<{ re: RegExp; record: ManagerPackRecord }>;
}

/** Resolve a missing node to its Manager pack: CNR/aux identity, preemptions, class, patterns. */
export function resolveManagerPack(
  node: Record<string, unknown>,
  index: ManagerPackIndex | null,
): ManagerPackRecord | null {
  if (!index || !node) return null;
  for (const raw of [node.cnr_id, node.aux_id]) {
    if (!raw) continue;
    const value = String(raw);
    const record =
      index.packs[value.toLowerCase()] ||
      index.packs[repoSlug(value)] ||
      index.packs[basename(value).toLowerCase()];
    if (record) return record;
  }
  const classes = Array.isArray(node.classes) ? node.classes : node.classes ? [node.classes] : [];
  const lowered = (classes as unknown[]).map((c) => String(c == null ? "" : c).toLowerCase()).filter(Boolean);
  for (const lc of lowered) {
    if (index.preemptions[lc]) return index.preemptions[lc];
  }
  for (const lc of lowered) {
    if (index.byClass[lc]) return index.byClass[lc];
  }
  for (const cls of classes as unknown[]) {
    const value = String(cls == null ? "" : cls);
    if (!value) continue;
    for (const pattern of index.patterns || []) {
      if (pattern.re.test(value)) return pattern.record;
    }
  }
  return null;
}

export type NodeInstallPlan =
  | { kind: "cnr"; pack: ManagerPackRecord; url: ""; name: string }
  | { kind: "git"; pack: null; url: string; name: string }
  | { kind: "none"; pack: null; url: ""; name: string };

/** Single explicit install target: Manager CNR queue, explicit-repo git fallback, or none. */
export function resolveNodeInstall(
  node: Record<string, unknown>,
  index: ManagerPackIndex | null,
): NodeInstallPlan {
  const pack = resolveManagerPack(node, index);
  if (pack) {
    return { kind: "cnr", pack, url: "", name: pack.name || String(node.name || "") };
  }
  const repo = String(node.repository_url || "");
  if (repo) {
    return { kind: "git", pack: null, url: repo, name: String(node.name || "") };
  }
  return { kind: "none", pack: null, url: "", name: String(node.name || "") };
}

function queueInstallPayload(pack: ManagerPackRecord): Record<string, unknown> {
  const files = Array.isArray(pack.files) ? pack.files.slice() : [];
  return {
    id: pack.cnrId || pack.repository || files[0] || "",
    version: pack.version || "unknown",
    selected_version: pack.selected_version || "latest",
    channel: pack.channel || "default",
    mode: pack.mode || "default",
    repository: pack.repository || files[0] || "",
    files,
    ui_id: String(pack.key || pack.cnrId || ""),
    install_type: pack.install_type || "",
    skip_post_install: false,
  };
}

/** Perform an explicit Manager install for a resolved plan. Never reboots. */
export async function performManagerInstall(
  plan: NodeInstallPlan,
): Promise<{ ok: boolean; message: string }> {
  if (!plan || plan.kind === "none") {
    return { ok: false, message: "No Manager install target identified for this pack." };
  }
  try {
    if (plan.kind === "cnr") {
      const queued = await managerQueueInstall(queueInstallPayload(plan.pack));
      if (!queued) return { ok: false, message: "Could not reach ComfyUI-Manager." };
      if (queued.status === 403) {
        return { ok: false, message: "Manager refused the CNR install (403). Raise Manager's security level, then retry." };
      }
      if (!queued.ok) {
        const data = queued.data as Record<string, unknown>;
        const msg = (data && (data.message || data.error)) || `HTTP ${queued.status}`;
        return { ok: false, message: `Install failed: ${String(msg)}` };
      }
      const started = await managerQueueStart();
      if (!started || !started.ok) {
        return { ok: false, message: "Install queued, but Manager did not start it. Open ComfyUI-Manager and press Start." };
      }
      return { ok: true, message: "Install queued through ComfyUI-Manager — restart ComfyUI to load it." };
    }
    const resp = await managerInstallNode(plan.url);
    if (!resp) return { ok: false, message: "Could not reach ComfyUI-Manager." };
    if (resp.status === 403) {
      return { ok: false, message: "Manager refused the install (403). Set allow_git_url_install=true, use a loopback session, then restart ComfyUI." };
    }
    if (resp.ok) return { ok: true, message: "Installed — restart ComfyUI to load it." };
    const data = resp.data as Record<string, unknown>;
    const msg = (data && (data.message || data.error)) || `HTTP ${resp.status}`;
    return { ok: false, message: `Install failed: ${String(msg)}` };
  } catch (err) {
    return { ok: false, message: `Install failed: ${(err as Error)?.message || "request failed"}` };
  }
}
