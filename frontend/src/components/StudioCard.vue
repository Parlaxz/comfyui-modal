<script setup lang="ts">
import { cn } from "./cn";
</script>

<template>
  <!-- Canonical Studio card panel: one raised container per region.
    Phase 4.5 depth budget is flat + hairlines, so no shadow here —
    overlays (dialogs) own the single elevation token. Radius 8
    (container role). Extra classes (e.g. padding) merge onto the
    root via fallthrough. -->
  <div
    :class="
      cn(
        'cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border ' +
          'cmst:bg-cmst-surface cmst:text-cmst-fg',
      )
    "
  >
    <slot />
  </div>
</template>
