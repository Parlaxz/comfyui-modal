<script setup lang="ts">
import { computed } from "vue";
import type { ControlSchemaEntry } from "../api/playground";

const props = defineProps<{
  schema: Record<string, ControlSchemaEntry>;
  values: Record<string, unknown>;
  hideRoles?: string[];
}>();

const emit = defineEmits<{
  update: [role: string, value: unknown];
  pickImage: [role: string];
  uploadImage: [role: string, file: File];
  clearImage: [role: string];
}>();

function entryOf(role: string): ControlSchemaEntry {
  return props.schema[role] ?? {};
}

function labelOf(role: string): string {
  const entry = entryOf(role);
  if (typeof entry.label === "string" && entry.label) return entry.label;
  return role
    .split("_")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}

function isPromptRole(role: string): boolean {
  return role === "prompt" || role === "negative_prompt" || role.endsWith("_prompt");
}

function isImageRole(role: string, entry: ControlSchemaEntry): boolean {
  if (role === "source_image" || role === "mask") return true;
  return entry.control_kind === "image";
}

function isSeedRole(role: string): boolean {
  return role === "seed";
}

function isResolutionRole(role: string): boolean {
  return role === "width" || role === "height";
}

function kindOf(role: string, entry: ControlSchemaEntry): string {
  if (isImageRole(role, entry)) return "image";
  if (isSeedRole(role)) return "seed";
  if (typeof entry.default === "boolean" || entry.data_type === "BOOLEAN") return "toggle";
  if (Array.isArray(entry.enum_options) && entry.enum_options.length) return "select";
  if (typeof entry.default === "number" || entry.data_type === "INT" || entry.data_type === "FLOAT") return "number";
  if (isPromptRole(role)) return "prompt";
  return "text";
}

const orderedRoles = computed(() => {
  const hidden = new Set(props.hideRoles ?? []);
  const roles = Object.keys(props.schema).filter(
    (role) => props.schema[role]?.enabled !== false && !hidden.has(role),
  );
  const rank = (role: string): number => {
    if (role === "prompt") return 0;
    if (role === "negative_prompt") return 1;
    if (isPromptRole(role)) return 2;
    if (role === "source_image" || role === "mask") return 3;
    if (isResolutionRole(role)) return 4;
    if (isSeedRole(role)) return 5;
    return 10;
  };
  return roles.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
});

const promptRoles = computed(() => orderedRoles.value.filter((role) => kindOf(role, entryOf(role)) === "prompt"));
const resolutionRoles = computed(() => orderedRoles.value.filter((role) => isResolutionRole(role)));
const imageRoles = computed(() =>
  orderedRoles.value.filter((role) => kindOf(role, entryOf(role)) === "image"),
);
const otherRoles = computed(() =>
  orderedRoles.value.filter(
    (role) =>
      !isPromptRole(role) &&
      !isResolutionRole(role) &&
      kindOf(role, entryOf(role)) !== "image" &&
      kindOf(role, entryOf(role)) !== "prompt",
  ),
);

function onFile(role: string, event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) emit("uploadImage", role, file);
  input.value = "";
}

function randomizeSeed(role: string): void {
  emit("update", role, Math.floor(Math.random() * 2 ** 31));
}

const inputClass =
  "cmst:h-9 cmst:w-full cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm cmst:text-cmst-fg";
const rowClass = "cmst:flex cmst:flex-col cmst:gap-1.5 cmst:py-2";
const labelClass = "cmst:text-[13px] cmst:font-medium cmst:text-cmst-secondary-text";
</script>

<template>
  <div data-testid="vue-playground-controls">
    <div v-if="!orderedRoles.length" class="cmst:py-4 cmst:text-sm cmst:opacity-70">
      This workflow exposes no controls yet. Map them in Workflows first.
    </div>

    <div v-for="role in promptRoles" :key="role" :class="rowClass">
      <label :for="`pg-ctl-${role}`" :class="labelClass">{{ labelOf(role) }}</label>
      <textarea
        :id="`pg-ctl-${role}`"
        :value="String(props.values[role] ?? '')"
        rows="3"
        :class="`${inputClass} cmst:h-auto cmst:py-2`"
        :data-testid="`vue-playground-control-${role}`"
        @input="emit('update', role, ($event.target as HTMLTextAreaElement).value)"
      />
    </div>

    <div v-if="imageRoles.length" class="cmst:flex cmst:flex-col cmst:gap-2 cmst:py-2">
      <div v-for="role in imageRoles" :key="role" :class="rowClass">
        <span :class="labelClass">{{ labelOf(role) }}</span>
        <div class="cmst:flex cmst:items-center cmst:gap-2">
          <span
            class="cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]"
            :data-testid="`vue-playground-control-${role}`"
          >
            {{ String(props.values[role] ?? "No image selected") }}
          </span>
          <button
            type="button"
            class="cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover"
            :data-testid="`vue-playground-pick-${role}`"
            @click="emit('pickImage', role)"
          >
            Browse
          </button>
          <label
            class="cmst:cursor-pointer cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover"
          >
            Upload
            <input type="file" accept="image/*" class="cmst:hidden" @change="onFile(role, $event)" />
          </label>
          <button
            v-if="props.values[role]"
            type="button"
            class="cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:opacity-70 cmst:hover:bg-cmst-hover"
            :data-testid="`vue-playground-clear-${role}`"
            @click="emit('clearImage', role)"
          >
            Clear
          </button>
        </div>
      </div>
    </div>

    <div v-if="resolutionRoles.length" class="cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:py-2">
      <div v-for="role in resolutionRoles" :key="role" :class="rowClass">
        <label :for="`pg-ctl-${role}`" :class="labelClass">{{ labelOf(role) }}</label>
        <input
          :id="`pg-ctl-${role}`"
          type="number"
          :value="Number(props.values[role] ?? entryOf(role).default ?? 0)"
          :min="entryOf(role).minimum"
          :max="entryOf(role).maximum"
          :step="entryOf(role).step ?? 1"
          :class="inputClass"
          :data-testid="`vue-playground-control-${role}`"
          @input="emit('update', role, Number(($event.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <div v-for="role in otherRoles" :key="role" :class="rowClass">
      <label
        v-if="kindOf(role, entryOf(role)) !== 'toggle'"
        :for="`pg-ctl-${role}`"
        :class="labelClass"
      >
        {{ labelOf(role) }}
      </label>
      <template v-if="kindOf(role, entryOf(role)) === 'toggle'">
        <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-[13px]">
          <input
            :id="`pg-ctl-${role}`"
            type="checkbox"
            :checked="Boolean(props.values[role] ?? entryOf(role).default ?? false)"
            :data-testid="`vue-playground-control-${role}`"
            @change="emit('update', role, ($event.target as HTMLInputElement).checked)"
          />
          {{ labelOf(role) }}
        </label>
      </template>
      <template v-else-if="kindOf(role, entryOf(role)) === 'select'">
        <select
          :id="`pg-ctl-${role}`"
          :value="String(props.values[role] ?? '')"
          :class="inputClass"
          :data-testid="`vue-playground-control-${role}`"
          @change="emit('update', role, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="opt in entryOf(role).enum_options ?? []" :key="String(opt)" :value="String(opt)">
            {{ String(opt) }}
          </option>
        </select>
      </template>
      <template v-else-if="kindOf(role, entryOf(role)) === 'seed'">
        <div class="cmst:flex cmst:items-center cmst:gap-2">
          <input
            :id="`pg-ctl-${role}`"
            type="number"
            :value="Number(props.values[role] ?? 0)"
            :class="inputClass"
            :data-testid="`vue-playground-control-${role}`"
            @input="emit('update', role, Number(($event.target as HTMLInputElement).value))"
          />
          <button
            type="button"
            class="cmst:shrink-0 cmst:rounded-lg cmst:px-2 cmst:py-1 cmst:text-[13px] cmst:hover:bg-cmst-hover"
            :data-testid="`vue-playground-randomize-${role}`"
            @click="randomizeSeed(role)"
          >
            Random
          </button>
        </div>
      </template>
      <template v-else-if="kindOf(role, entryOf(role)) === 'number'">
        <input
          :id="`pg-ctl-${role}`"
          type="number"
          :value="Number(props.values[role] ?? entryOf(role).default ?? 0)"
          :min="entryOf(role).minimum"
          :max="entryOf(role).maximum"
          :step="entryOf(role).step ?? 1"
          :class="inputClass"
          :data-testid="`vue-playground-control-${role}`"
          @input="emit('update', role, Number(($event.target as HTMLInputElement).value))"
        />
      </template>
      <template v-else>
        <input
          :id="`pg-ctl-${role}`"
          type="text"
          :value="String(props.values[role] ?? '')"
          :class="inputClass"
          :data-testid="`vue-playground-control-${role}`"
          @input="emit('update', role, ($event.target as HTMLInputElement).value)"
        />
      </template>
    </div>
  </div>
</template>
