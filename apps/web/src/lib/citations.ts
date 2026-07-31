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

// Sigle canoniche: DEVE restare allineata a _SOURCE_SUFFIX in
// services/rag-core/.../schemas/citation.py (test: citations.test.ts).
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
  dlgs231: "D.Lgs. 231/2001",
  aml: "D.Lgs. 231/2007",
  l190: "L. 190/2012",
  dlgs33: "D.Lgs. 33/2013",
  dlgs39: "D.Lgs. 39/2013",
  cam: "cod. antimafia",
  wb: "D.Lgs. 24/2023",
  ritpag: "D.Lgs. 231/2002",
  tua: "TU ambiente",
  tupi: "TU pubbl. imp.",
  cpa: "c.p.a.",
  cpt: "D.Lgs. 546/1992",
  tuel: "TUEL",
  tudoc: "D.P.R. 445/2000",
  cbc: "cod. beni cult.",
  cap: "cod. ass.",
  iva: "D.P.R. 633/1972",
  dpr600: "D.P.R. 600/1973",
  lav81: "D.Lgs. 81/2015",
  l604: "L. 604/1966",
  dlgs23: "D.Lgs. 23/2015",
  tumat: "TU maternità",
  l392: "L. 392/1978",
  l898: "L. 898/1970",
  l76: "L. 76/2016",
  l91: "L. 91/1992",
  cnav: "cod. nav.",
  gdpr: "GDPR",
  aiact: "AI Act",
  nis2: "dir. NIS2",
  dora: "reg. DORA",
  mica: "reg. MiCA",
  eidas: "reg. eIDAS",
  dsa: "reg. DSA",
  dma: "reg. DMA",
  dircons: "dir. 2011/83/UE",
  wbdir: "dir. (UE) 2019/1937",
  amld: "dir. (UE) 2015/849",
  psd2: "PSD2",
  eprivacy: "dir. ePrivacy",
  mifid2: "MiFID II",
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
