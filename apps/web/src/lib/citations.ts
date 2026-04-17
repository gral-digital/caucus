/**
 * Gestione delle citazioni normative nel testo LLM.
 *
 * Il modello emette tag machine-readable del tipo:
 *   <cite source="cc" part="articolo" num="2043" comma="1" letter="a"/>
 *
 * Strategia: PRIMA di passare il testo al renderer Markdown, trasformiamo i
 * tag <cite/> in link Markdown normali `[display](href)`. In questo modo
 * react-markdown renderizza correttamente bold/liste/paragrafi *e* le
 * citazioni, senza doppio parsing.
 *
 * Export `preprocessCitations(text)` → testo Markdown valido.
 */

const CITE_RE =
  /<cite\s+source="([a-z0-9-]+)"\s+part="([a-z]+)"\s+num="([^"]+)"(?:\s+comma="([^"]+)")?(?:\s+letter="([^"]+)")?\s*\/>/gi;

const SUFFIX: Record<string, string> = {
  cc: "c.c.",
  cp: "c.p.",
  cpc: "c.p.c.",
  cpp: "c.p.p.",
  cost: "Cost.",
  cds: "cod. strada",
  cdc: "cod. cons.",
  ccii: "CCII",
  ccp: "cod. contr. pubbl.",
  cad: "CAD",
  cts: "CTS",
  tus: "TU stup.",
  tui: "TU imm.",
  tue: "TU ed.",
  tusl: "TU sic. lav.",
  tub: "TUB",
  tuf: "TUF",
  tuir: "TUIR",
  cpriv: "cod. privacy",
  l241: "L. 241/1990",
  stat: "St. Lav.",
  l689: "L. 689/1981",
  lpf: "L. 247/2012",
};

export function buildCitationDisplay(
  source: string,
  num: string,
  comma?: string,
  letter?: string,
): string {
  const parts = [`art. ${num}`];
  if (comma) parts.push(`c. ${comma}`);
  if (letter) parts.push(`lett. ${letter})`);
  const suffix = SUFFIX[source] ?? source;
  return `${parts.join(", ")} ${suffix}`;
}

export function buildCitationHref(
  source: string,
  num: string,
  comma?: string,
  letter?: string,
): string {
  let href = `/norma/${source}/art/${num}`;
  const frag: string[] = [];
  if (comma) frag.push(`c${comma}`);
  if (letter) frag.push(`l${letter}`);
  if (frag.length > 0) href += `#${frag.join("-")}`;
  return href;
}

/**
 * Sostituisce ogni tag <cite/> con un link Markdown.
 *
 * Escape parentesi nel display per evitare di rompere la sintassi link MD.
 */
export function preprocessCitations(raw: string): string {
  return raw.replace(
    CITE_RE,
    (_full, source: string, _part: string, num: string, comma?: string, letter?: string) => {
      const display = buildCitationDisplay(source, num, comma, letter).replace(
        /([[\]()])/g,
        "\\$1",
      );
      const href = buildCitationHref(source, num, comma, letter);
      return `[${display}](${href})`;
    },
  );
}
