<script setup lang="ts">
import { studioButtonVariants, type StudioButtonVariants } from "./StudioButton";

interface StudioButtonProps {
  variant?: StudioButtonVariants["variant"];
  size?: StudioButtonVariants["size"];
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
}

withDefaults(defineProps<StudioButtonProps>(), {
  variant: "default",
  size: "default",
  type: "button",
  disabled: false,
});
</script>

<template>
  <!-- Canonical Studio button. Native click/focus/disabled behavior passes
    through untouched; extra attributes (data-testid, aria-*) fall through
    to the root. Variants live in ./StudioButton (cva, cmst: prefix). -->
  <button
    :type="type"
    :disabled="disabled"
    :class="studioButtonVariants({ variant, size })"
  >
    <slot />
  </button>
</template>
