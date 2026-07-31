"""Test parsing del fetcher Giustizia Amministrativa (risultati + documento)."""

from __future__ import annotations

from caucus_ingestion.fetchers.giustizia_amministrativa import (
    _extract_document_text,
    _parse_results,
)

_RESULTS_HTML = """
<html><body>
<div class="result">
  <a href="https://mdp.giustizia-amministrativa.it/visualizza/?nodeRef=&schema=cds&nrg=202602793&nomeFile=202606189_11.html&subDir=Provvedimenti">202606189</a>
  <p>SENTENZA sede di CONSIGLIO DI STATO, sezione SEZIONE 4, numero provv.: 202606189 ,
  Numero ricorso: 202602793 ECLI:IT:CDS:2026:6189SENT</p>
</div>
<div class="result">
  <a href="https://mdp.giustizia-amministrativa.it/visualizza/?nodeRef=&schema=tar_rm&nrg=202604902&nomeFile=202613993_01.html&subDir=Provvedimenti">202613993</a>
  <p>SENTENZA sede di ROMA, sezione SEZIONE 5, numero provv.: 202613993 ,
  Numero ricorso: 202604902 ECLI:IT:TARLAZ:2026:13993SENT</p>
</div>
<div class="result">
  <a href="https://mdp.giustizia-amministrativa.it/visualizza/?nodeRef=&schema=tar_rm&nrg=202602645&nomeFile=202613624_01.pdf&subDir=Provvedimenti">202613624 (pdf)</a>
  <p>SENTENZA sede di ROMA, sezione SEZIONE 2, numero provv.: 202613624</p>
</div>
</body></html>
"""


def test_parse_results_extracts_metadata():
    docs = _parse_results(_RESULTS_HTML)
    # Il PDF è scartato in v1
    assert len(docs) == 2
    cds, tar = docs
    assert cds.external_id == "ECLI:IT:CDS:2026:6189SENT"
    assert cds.sede == "CONSIGLIO DI STATO"
    assert cds.sezione == "SEZIONE 4"
    assert cds.numero == "202606189"
    assert cds.anno == 2026
    assert cds.nrg == "202602793"
    assert tar.external_id == "ECLI:IT:TARLAZ:2026:13993SENT"
    assert tar.sede == "ROMA"


def test_parse_results_dedups_repeated_links():
    docs = _parse_results(_RESULTS_HTML + _RESULTS_HTML)
    assert len(docs) == 2


_DOC_HTML = (
    "<html><body><div>202602793.xml\nU:\\DocumentiGA\\Magistrati\\304\\\noperatore rossi\n"
    "<p>Il Consiglio di Stato</p><p>in sede giurisdizionale (Sezione Quarta)</p>"
    "<p>ha pronunciato la presente SENTENZA sul ricorso numero di registro generale 2793 del 2026</p>"
    "<p>" + ("Considerato che il provvedimento impugnato risulta motivato. " * 30) + "</p>"
    "<p>P.Q.M. il Consiglio di Stato respinge il ricorso.</p></div></body></html>"
)


def test_extract_document_text_trims_internal_metadata():
    text = _extract_document_text(_DOC_HTML)
    assert text is not None
    assert text.startswith("Il Consiglio di Stato")
    # I metadati interni del gestionale non devono sopravvivere
    assert "DocumentiGA" not in text
    assert "operatore" not in text
    assert "P.Q.M." in text


def test_extract_document_text_rejects_pages_without_marker():
    assert _extract_document_text("<html><body>Errore 404" + "x" * 1000 + "</body></html>") is None
