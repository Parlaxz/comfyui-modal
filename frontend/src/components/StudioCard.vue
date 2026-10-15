<script setup lang="ts">
import { cn } from "./cn";
</script>

<template>
  <!-- Canonical Studio card panel. One panel look for proof views and
    future pages: rounded surface, Studio border token, subtle shadow.
    Extra classes (e.g. padding) merge onto the root via fallthrough. -->
  <div
    :class="
      cn(
        'cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border ' +
          'cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm',
      )
    "
  >
    <slot />
  </div>
</template>
