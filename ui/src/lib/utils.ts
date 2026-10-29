import { clsx, type ClassValue } from "clsx";

/**
  Joins class names, dropping the falsy ones.

  This used to run the result through tailwind-merge, which resolves conflicts ("size-8" against
  "size-10": the later one wins). Nothing here relies on that any more, and the package was about
  9 KB gzipped of the first download, so the conflicts are avoided instead: a component that takes
  a `className` must not ask for something its own classes already set (AgentAvatar takes a
  `size` for that reason). A later class does NOT override an earlier one: CSS order decides.
*/
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
