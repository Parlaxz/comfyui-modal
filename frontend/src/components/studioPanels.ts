// StudioCard + PageShell — minimal shared panel primitives for the Phase-1
// proof views. Deliberately plain Vue renderless-class helpers (not a
// component framework): one panel look, one page layout, nothing more.
import { cn } from "./cn";

export function studioCardClass(extra?: string): string {
  return cn(
    "cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border " +
      "cmst:bg-cmst-surface cmst:text-cmst-fg cmst:shadow-sm",
    extra,
  );
}

export function studioPageClass(extra?: string): string {
  return cn(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-4 cmst:sm:p-6",
    extra,
  );
}
