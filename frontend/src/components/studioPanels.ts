// Studio page shell — the one shared page-layout helper for the Phase-1
// proof views (vertical stack with breathing room). Card panels render
// through the canonical `./StudioCard.vue` SFC, not through class helpers.
import { cn } from "./cn";

export function studioPageClass(extra?: string): string {
  return cn(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    extra,
  );
}
