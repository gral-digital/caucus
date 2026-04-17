/**
 * Parser e renderer per citazioni machine-readable nel testo LLM.
 *
 * Il modello emette tag canonici della forma:
 *   <cite source="cc" part="articolo" num="2043" comma="1" />
 *
 * Li convertiamo in segmenti typed che il componente di rendering trasforma
 * in link cliccabili verso il browser normativo.
 */

const CITE_RE =
  /<cite\s+source="([a-z0-9-]+)"\s+part="([a-z]+)"\s+num="([^"]+)"(?:\s+comma="([^"]+)")?(?:\s+letter="([^"]+)")?\s*\/>/gi;

export type CitationSegment =
  | { kind: "text"; text: string }
  | {
      kind: "cite";
      source: string;
      part: string;
      num: string;
      comma?: string;
      letter?: string;
      display: string;
      href: string;
    };

const SUFFIX: Record<string, string> = {
  cc: "c.c.",
  cp: "c.p.",
  cpc: "c.p.c.",
  cpp: "c.p.p.",
  cost: "Cost.",
};

export function parseCitations(raw: string): CitationSegment[] {
  const segments: CitationSegment[] = [];
  let lastIndex = 0;

  for (const match of raw.matchAll(CITE_RE)) {
    const [full, source, part, num, comma, letter] = match;
    const idx = match.index ?? 0;
    if (idx > lastIndex) {
      segments.push({ kind: "text", text: raw.slice(lastIndex, idx) });
    }

    const parts = [`art. ${num}`];
    if (comma) parts.push(`c. ${comma}`);
    if (letter) parts.push(`lett. ${letter})`);
    const suffix = SUFFIX[source] ?? source;
    const display = `${parts.join(", ")} ${suffix}`;

    let href = `/norma/${source}/art/${num}`;
    const frag: string[] = [];
    if (comma) frag.push(`c${comma}`);
    if (letter) frag.push(`l${letter}`);
    if (frag.length > 0) href += `#${frag.join("-")}`;

    segments.push({
      kind: "cite",
      source,
      part,
      num,
      comma,
      letter,
      display,
      href,
    });
    lastIndex = idx + full.length;
  }

  if (lastIndex < raw.length) {
    segments.push({ kind: "text", text: raw.slice(lastIndex) });
  }
  return segments;
}
