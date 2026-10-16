// Studio page shell — fullscreen workspace gutter: 24px page inset (32px on
// wide), so content never glues to the frame edge and dead zones stay small.
import { cn } from "./cn";

export function studioPageClass(extra?: string): string {
  return cn(
    "cmst:flex cmst:flex-col cmst:gap-4 cmst:p-6 cmst:sm:p-8",
    extra,
  );
}
