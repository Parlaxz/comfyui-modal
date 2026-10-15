// StudioButton variants — shadcn-vue-style button (cva variants, `cmst:` prefix).
//
// Follows the shadcn-vue generated-component conventions (variant/size via
// class-variance-authority, `cn()` merging) while using the Studio-scoped
// Tailwind prefix so no class can collide with ComfyUI or old Studio CSS.
//
// The canonical Button is the `./StudioButton.vue` SFC, which applies these
// variants. Render buttons through the SFC, not by hand-rolling classes.
import { cva, type VariantProps } from "class-variance-authority";

export const studioButtonVariants = cva(
  "cmst:inline-flex cmst:items-center cmst:justify-center cmst:gap-2 cmst:whitespace-nowrap cmst:rounded-md cmst:text-sm cmst:font-medium cmst:transition-colors cmst:cursor-pointer cmst:disabled:pointer-events-none cmst:disabled:opacity-50 cmst:[&_svg]:size-4 cmst:[&_svg]:shrink-0 cmst:outline-none cmst:border cmst:border-solid",
  {
    variants: {
      variant: {
        default:
          "cmst:bg-cmst-primary cmst:text-cmst-primary-fg cmst:border-transparent cmst:hover:bg-cmst-primary-hover",
        secondary:
          "cmst:bg-cmst-secondary cmst:text-cmst-secondary-fg cmst:border-cmst-border cmst:hover:bg-cmst-secondary-hover",
        outline:
          "cmst:bg-transparent cmst:text-cmst-fg cmst:border-cmst-border cmst:hover:bg-cmst-secondary",
        ghost:
          "cmst:bg-transparent cmst:text-cmst-fg cmst:border-transparent cmst:hover:bg-cmst-secondary",
      },
      size: {
        default: "cmst:h-9 cmst:px-4 cmst:py-2",
        sm: "cmst:h-8 cmst:px-3 cmst:text-xs",
        lg: "cmst:h-10 cmst:px-6",
        icon: "cmst:h-9 cmst:w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export type StudioButtonVariants = VariantProps<typeof studioButtonVariants>;
