"""Test unitari del parser AKN su frammenti XML sintetici.

Complementa i test su fixture reali. Verifica edge cases specifici senza
dipendere dalle fixture grandi.
"""

from __future__ import annotations

import textwrap

from avvocato_ingestion.parsers.normattiva_akn import NormattivaAknParser


def _make_minimal_akn(attachments: list[tuple[str, str]]) -> bytes:
    """Costruisce un AKN XML minimale con solo gli attachments passati.

    Args:
        attachments: lista di tuple ``(doc_name, full_text)``.
    """
    att_xml = "".join(
        textwrap.dedent(
            f"""
            <attachment>
              <doc name="{name}">
                <mainBody>
                  <paragraph>
                    <content>
                      <p>{text}</p>
                    </content>
                  </paragraph>
                </mainBody>
              </doc>
            </attachment>
            """
        )
        for name, text in attachments
    )
    xml = textwrap.dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
          <act>
            <meta/>
            <body/>
            <attachments>
              {att_xml}
            </attachments>
          </act>
        </akomaNtoso>
        """
    )
    # NB: l'interpolazione di att_xml azzera il prefisso comune, quindi il
    # dedent non rimuove l'indentazione della prima riga: lxml rifiuta
    # whitespace prima della dichiarazione XML. Strip esplicito.
    return xml.strip().encode("utf-8")


def test_parses_rubrica_between_parens():
    xml = _make_minimal_akn(
        [
            (
                "CODICE CIVILE-art. 2043",
                " Art. 2043. \n \n (Risarcimento per fatto illecito). \n \n Qualunque fatto doloso o colposo.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cc")
    art = act.root[0].children[0]
    assert art.number == "2043"
    assert art.rubrica == "Risarcimento per fatto illecito"
    assert len(art.commi) == 1
    assert "Qualunque fatto" in art.commi[0].text


def test_parses_rubrica_with_double_parens_modifica():
    xml = _make_minimal_akn(
        [
            (
                "CODICE CIVILE-art. 414",
                " Art. 414. \n \n (( (Persone che possono essere interdette). ))\n Il maggiore di età.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cc")
    art = act.root[0].children[0]
    assert art.rubrica == "Persone che possono essere interdette"


def test_parses_rubrica_without_parens_plain_line():
    xml = _make_minimal_akn(
        [
            (
                "Codice Penale-art. 416 bis",
                " Art. 416-bis. \n \n Associazioni di tipo mafioso anche straniere \n \n Chiunque fa parte.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cp")
    art = act.root[0].children[0]
    assert art.number == "416-bis"
    assert art.rubrica == "Associazioni di tipo mafioso anche straniere"


def test_rubrica_with_internal_period_in_parens():
    """Es. art. 81 CP: '(Concorso formale. Reato continuato).'"""
    xml = _make_minimal_akn(
        [
            (
                "Codice Penale-art. 81",
                " Art. 81. \n \n (Concorso formale. Reato continuato). \n \n È punito.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cp")
    art = act.root[0].children[0]
    assert art.rubrica == "Concorso formale. Reato continuato"


def test_strip_aggiornamenti_from_commi():
    """Le note AGGIORNAMENTO non devono diventare commi."""
    xml = _make_minimal_akn(
        [
            (
                "Codice Penale-art. 575",
                " Art. 575. \n \n (Omicidio) \n \n Chiunque cagiona la morte. \n\n -----------\nAGGIORNAMENTO (96)\n La L. 31 maggio 1965 ha disposto.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cp")
    art = act.root[0].children[0]
    assert art.rubrica == "Omicidio"
    for c in art.commi:
        assert "AGGIORNAMENTO" not in c.text


def test_article_number_with_bis():
    xml = _make_minimal_akn(
        [
            (
                "CODICE CIVILE-art. 2929 bis",
                " Art. 2929-bis. \n \n (Test). \n \n Testo.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cc")
    assert act.root[0].children[0].number == "2929-bis"


def test_multiple_commi_numbered():
    xml = _make_minimal_akn(
        [
            (
                "CODICE CIVILE-art. 1418",
                " Art. 1418. \n \n (Cause di nullità del contratto). \n \n"
                "1. Primo comma.\n\n"
                "2. Secondo comma.\n\n"
                "3. Terzo comma.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cc")
    commi = act.root[0].children[0].commi
    assert len(commi) == 3
    assert commi[0].number == "1"
    assert commi[1].number == "2"
    assert commi[2].number == "3"
    assert "Primo comma" in commi[0].text


def test_article_without_rubrica():
    xml = _make_minimal_akn(
        [
            (
                "CODICE CIVILE-art. 17",
                " Art. 17. \n \n ARTICOLO ABROGATO DALLA L. 31 MAGGIO 1995, N. 218.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cc")
    art = act.root[0].children[0]
    # Abrogated article: rubrica None is acceptable (abrogazione non ha rubrica)
    # ma l'articolo deve comunque essere estratto
    assert art.number == "17"


def test_article_number_slash_form():
    """CC storico: 'art. 314/2' non deve collassare su '314'."""
    xml = _make_minimal_akn(
        [
            (
                "CODICE CIVILE-art. 314/2",
                " Art. 314/2. \n \n ARTICOLO ABROGATO DALLA L. 4 MAGGIO 1983, N. 184.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cc")
    art = act.root[0].children[0]
    assert art.number == "314/2"
    assert art.abrogato is True


def test_article_number_beyond_decies():
    """Codice Privacy: 2-undecies e 2-quaterdecies.1 non devono collassare."""
    xml = _make_minimal_akn(
        [
            ("X-art. 2 undecies", " Art. 2-undecies. \n \n (Limitazioni). \n \n Testo."),
            ("X-art. 2 quaterdecies", " Art. 2-quaterdecies. \n \n (Autorizzati). \n \n Testo."),
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cpriv")
    nums = [a.number for a in act.root[0].children]
    assert nums == ["2-undecies", "2-quaterdecies"]


def test_abrogato_flag_not_set_on_vigente():
    xml = _make_minimal_akn(
        [
            (
                "CODICE CIVILE-art. 2043",
                " Art. 2043. \n \n (Risarcimento). \n \n Qualunque fatto doloso o colposo"
                " che menziona norme abrogate resta vigente.",
            )
        ]
    )
    act = NormattivaAknParser().parse_bytes(xml, short_id="cc")
    assert act.root[0].children[0].abrogato is False
