import { describe, expect, it } from "vitest";

import { buildCitationDisplay, buildCitationHref, preprocessCitations } from "./citations";

describe("buildCitationDisplay", () => {
  it("usa la sigla canonica della fonte", () => {
    expect(buildCitationDisplay("cc", "2043")).toBe("art. 2043 c.c.");
    expect(buildCitationDisplay("cp", "575")).toBe("art. 575 c.p.");
  });

  it("copre anche le fonti UE e di compliance", () => {
    expect(buildCitationDisplay("gdpr", "6")).toBe("art. 6 GDPR");
    expect(buildCitationDisplay("dlgs231", "6")).toBe("art. 6 D.Lgs. 231/2001");
    expect(buildCitationDisplay("aiact", "5")).toBe("art. 5 AI Act");
  });

  it("include comma e lettera quando presenti", () => {
    expect(buildCitationDisplay("cc", "2043", "1", "a")).toBe("art. 2043, c. 1, lett. a) c.c.");
  });

  it("per una fonte sconosciuta non inventa: usa lo short_id", () => {
    expect(buildCitationDisplay("xyz", "1")).toBe("art. 1 xyz");
  });
});

describe("buildCitationHref", () => {
  it("punta alla route /norma con fragment comma/lettera", () => {
    expect(buildCitationHref("cc", "2043")).toBe("/norma/cc/art/2043");
    expect(buildCitationHref("cc", "2043", "1")).toBe("/norma/cc/art/2043#c1");
    expect(buildCitationHref("cc", "2043", "1", "a")).toBe("/norma/cc/art/2043#c1-la");
  });

  it("gestisce i numeri con suffisso latino", () => {
    expect(buildCitationHref("cp", "612-bis")).toBe("/norma/cp/art/612-bis");
  });
});

describe("preprocessCitations", () => {
  it("trasforma i tag <cite/> in link Markdown", () => {
    const out = preprocessCitations(
      'Vedi <cite source="cc" part="articolo" num="2043"/> per il danno.',
    );
    expect(out).toContain("[art. 2043 c.c.](/norma/cc/art/2043)");
    expect(out).not.toContain("<cite");
  });

  it("gestisce più citazioni nello stesso testo", () => {
    const out = preprocessCitations(
      '<cite source="cp" part="articolo" num="575"/> e <cite source="cp" part="articolo" num="589"/>',
    );
    expect(out).toContain("/norma/cp/art/575");
    expect(out).toContain("/norma/cp/art/589");
  });

  it("lascia intatto il testo senza citazioni", () => {
    const text = "Nessuna citazione qui, solo **markdown**.";
    expect(preprocessCitations(text)).toBe(text);
  });
});
