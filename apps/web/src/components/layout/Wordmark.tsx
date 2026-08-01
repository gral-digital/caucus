import { cn } from "@/lib/cn";

/**
 * Wordmark tipografico: niente icona, solo carattere.
 * Serif minuscolo a tracking stretto con punto finale in accent: il punto
 * è la firma («caucus.»), come i marchi di studio.
 */
export function Wordmark({
  className,
  size = "md",
}: {
  className?: string;
  size?: "md" | "lg";
}) {
  return (
    <span
      className={cn(
        "font-serif font-medium lowercase tracking-[-0.03em] text-ink",
        size === "md" ? "text-[21px]" : "text-[26px]",
        className,
      )}
    >
      caucus<span className="text-accent">.</span>
    </span>
  );
}
