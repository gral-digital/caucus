"""Parser Akoma Ntoso XML servito da Normattiva.

Normattiva pubblica i testi consolidati vigenti come AKN XML (standard OASIS).
Il formato servito da Normattiva usa questa struttura semplificata:

    <akomaNtoso>
      <act>
        <meta>...</meta>
        <body>
          <article>...</article>    <!-- regio decreto di approvazione, 2 articoli -->
        </body>
        <attachments>
          <attachment>                <!-- un attachment per ARTICOLO del codice -->
            <doc name="CODICE CIVILE-art. 2043">
              <meta>...</meta>
              <mainBody>
                <paragraph>           <!-- un solo <paragraph> container -->
                  <content>
                    <p> Art. 2043. \n \n (Rubrica). \n \n comma1 \n \n comma2 ... </p>
                  </content>
                </paragraph>
              </mainBody>
            </doc>
          </attachment>
          ...
        </attachments>
      </act>
    </akomaNtoso>

Quindi:
- Ogni `<attachment>` = un articolo (o pre-disposizione).
- Il testo completo dell'articolo è concatenato in un singolo `<p>` con commi
  separati da ` \n \n `.
- Le modifiche sono marcate con `(( ... ))` — le conserviamo inline (il
  contenuto tra doppie parentesi è testo modificato tuttora vigente).

La gerarchia Libro/Titolo/Capo/Sezione NON è codificata a livello di articolo
nell'XML. Per il primo indice la manteniamo semplice (root = "Codice Civile",
children = articoli). La gerarchia completa verrà arricchita da una seconda
pass sull'indice HTML (TODO — non blocca il RAG base).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator

import structlog
from lxml import etree

from avvocato_ingestion.canonical import (
    CanonicalAct,
    CanonicalComma,
    CanonicalCommaLetter,
    CanonicalPartition,
)
from avvocato_rag_core.schemas.norm import NormPartitionKind, NormSourceType

logger = structlog.get_logger(__name__)

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"a": AKN_NS}


# Metadati canonici per codici conosciuti. Sono i dati sorgente autorevoli che
# l'XML *non* codifica (es. short_id + data emanazione standardizzata).
@dataclass(frozen=True, slots=True)
class CodiceInfo:
    short_id: str
    urn: str
    title: str
    issued_at: date
    in_force_from: date


CODICI_CATALOG: dict[str, CodiceInfo] = {
    "cc": CodiceInfo(
        short_id="cc",
        urn="urn:nir:stato:regio.decreto:1942-03-16;262",
        title="Codice Civile",
        issued_at=date(1942, 3, 16),
        in_force_from=date(1942, 4, 21),
    ),
    "cp": CodiceInfo(
        short_id="cp",
        urn="urn:nir:stato:regio.decreto:1930-10-19;1398",
        title="Codice Penale",
        issued_at=date(1930, 10, 19),
        in_force_from=date(1931, 7, 1),
    ),
    "cpc": CodiceInfo(
        short_id="cpc",
        urn="urn:nir:stato:regio.decreto:1940-10-28;1443",
        title="Codice di Procedura Civile",
        issued_at=date(1940, 10, 28),
        in_force_from=date(1942, 4, 21),
    ),
    "cpp": CodiceInfo(
        short_id="cpp",
        urn="urn:nir:stato:decreto.del.presidente.della.repubblica:1988-09-22;447",
        title="Codice di Procedura Penale",
        issued_at=date(1988, 9, 22),
        in_force_from=date(1989, 10, 24),
    ),
}


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# "art. 2043" oppure "art. 2043-bis" oppure "2043 bis"
_ARTICLE_NUM_RE = re.compile(
    r"art\.\s*([0-9]+(?:[-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?)",
    re.IGNORECASE,
)

# Una linea "Art. 2043." a inizio testo (preceduta da opt. whitespace)
_ART_HEADER_RE = re.compile(
    r"^\s*Art\.?\s*([0-9]+(?:[-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?)\s*\.?\s*",
    re.IGNORECASE,
)

# Rubrica modificata: "(( (Rubrica). ))" con doppie parentesi da aggiornamento.
_RUBRICA_MOD_RE = re.compile(
    r"^\s*\(\(\s*\(\s*([^()]+?)\s*\)\s*\.?\s*\)\)\s*\.?\s*",
    re.DOTALL,
)

# Rubrica standard: "(Rubrica)." (parentesi singole).
_RUBRICA_STD_RE = re.compile(
    r"^\s*\(\s*([^()]+?)\s*\)\s*\.?\s*",
    re.DOTALL,
)

# Marcatore di aggiornamenti Normattiva: linea "-----------" seguita da
# "AGGIORNAMENTO (N)". Tutto ciò che segue NON è testo normativo vigente ma
# note di modifica storica — lo isoliamo in metadata, non entra nei commi.
_AGGIORNAMENTO_SEP_RE = re.compile(
    r"\n\s*-{5,}\s*\n\s*AGGIORNAMENTO\s*\(\s*\d+\s*\)",
    re.IGNORECASE,
)

# Split commi: numerazione all'inizio di linea/blocco "N. " oppure "Nbis. "
_COMMA_NUM_RE = re.compile(
    r"(?:^|\n\s*\n)\s*"
    r"([0-9]+(?:[-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?)"
    r"\s*\.\s+",
    re.IGNORECASE,
)

# Lettere dentro un comma: " a) " " b) "
_LETTER_RE = re.compile(r"(?:^|\n\s*|\s+)([a-z])\)\s+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class NormattivaAknParser:
    """Parser dell'XML AKN per codici serviti da Normattiva."""

    def __init__(self, *, keep_modification_markers: bool = False) -> None:
        """
        Args:
            keep_modification_markers: se True, conserva le doppie parentesi
                `(( ... ))` che Normattiva usa per marcare testo modificato da
                atti successivi. Default False (testo pulito).
        """
        self._keep_markers = keep_modification_markers

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def parse_file(self, xml_path: Path, *, short_id: str) -> CanonicalAct:
        """Parsa un file AKN salvato localmente."""
        xml_bytes = xml_path.read_bytes()
        return self.parse_bytes(xml_bytes, short_id=short_id)

    def parse_bytes(self, xml_bytes: bytes, *, short_id: str) -> CanonicalAct:
        if short_id not in CODICI_CATALOG:
            raise ValueError(f"Unknown codice short_id: {short_id!r}")
        info = CODICI_CATALOG[short_id]

        tree = etree.fromstring(xml_bytes)
        articles = list(self._iter_articles(tree))
        logger.info(
            "akn.parsed",
            short_id=short_id,
            articles=len(articles),
            size_bytes=len(xml_bytes),
        )

        # Wrap in a single root partition = il codice stesso.
        # La gerarchia Libro/Titolo/Capo verrà arricchita in un secondo passaggio
        # (TODO: parsing dell'indice HTML). Per ora: flat list di articoli.
        root = CanonicalPartition(
            kind=NormPartitionKind.LIBRO,  # usiamo 'libro' come stand-in per il root code
            number="0",
            label=info.title,
            rubrica=None,
            full_text=None,
            commi=[],
            children=articles,
        )

        return CanonicalAct(
            urn=info.urn,
            short_id=info.short_id,
            title=info.title,
            type=NormSourceType.CODICE,
            issued_at=info.issued_at,
            in_force_from=info.in_force_from,
            in_force_to=None,
            source_url=f"https://www.normattiva.it/uri-res/N2Ls?{info.urn}",
            source_hash=hashlib.sha256(xml_bytes).hexdigest(),
            root=[root],
        )

    # ------------------------------------------------------------------
    # Article extraction
    # ------------------------------------------------------------------

    def _iter_articles(self, root: etree._Element) -> Iterator[CanonicalPartition]:
        """Itera gli articoli come CanonicalPartition."""
        attachments = root.findall(".//a:act/a:attachments/a:attachment", _NS)
        for att in attachments:
            doc = att.find("a:doc", _NS)
            if doc is None:
                continue
            article = self._parse_article_doc(doc)
            if article is not None:
                yield article

    def _parse_article_doc(self, doc: etree._Element) -> CanonicalPartition | None:
        name = doc.get("name", "")
        num = self._extract_article_number(name)
        if num is None:
            return None

        main_body = doc.find("a:mainBody", _NS)
        if main_body is None:
            return None

        raw_text = self._extract_full_text(main_body)
        if not raw_text.strip():
            return None

        # Separa testo vigente dalle note di aggiornamento (che Normattiva
        # accoda dopo il testo normativo vero).
        vigente_text, aggiornamenti_text = self._strip_aggiornamenti(raw_text)

        rubrica, body = self._split_rubrica(vigente_text, num)
        commi = self._split_commi(body)
        full_text = self._clean_markers(vigente_text)

        metadata = {"source": "normattiva"}
        if aggiornamenti_text:
            metadata["aggiornamenti"] = self._clean_markers(aggiornamenti_text)

        return CanonicalPartition(
            kind=NormPartitionKind.ARTICOLO,
            number=num,
            label=f"art. {num}",
            rubrica=rubrica,
            full_text=full_text,
            commi=commi,
        )

    @staticmethod
    def _strip_aggiornamenti(raw_text: str) -> tuple[str, str | None]:
        """Separa testo vigente da note di aggiornamento.

        Normattiva accoda i ``----------- AGGIORNAMENTO (N)`` con descrizione
        delle modifiche storiche dopo il testo normativo. Li separiamo così il
        retriever non li include come commi.
        """
        m = _AGGIORNAMENTO_SEP_RE.search(raw_text)
        if not m:
            return raw_text, None
        return raw_text[: m.start()], raw_text[m.start() :]

    # ------------------------------------------------------------------
    # Text extraction + cleanup
    # ------------------------------------------------------------------

    def _extract_full_text(self, element: etree._Element) -> str:
        """Estrae tutto il testo concatenando itertext()."""
        parts: list[str] = []
        for t in element.itertext():
            if t:
                parts.append(t)
        return "".join(parts)

    def _extract_article_number(self, attachment_name: str) -> str | None:
        """Estrae il numero dall'attribute `name` dell'attachment."""
        m = _ARTICLE_NUM_RE.search(attachment_name)
        if not m:
            return None
        raw = m.group(1).strip()
        # Normalizza spaziatura: "2043 bis" → "2043-bis"
        raw = re.sub(r"\s+", "-", raw)
        return raw.lower()

    def _split_rubrica(self, text: str, article_num: str) -> tuple[str | None, str]:
        """Separa la rubrica dall'articolo.

        Formati gestiti:
          1. Standard:       ``Art. 2043. \\n (Risarcimento per fatto illecito). \\n ...``
          2. Con aggiornam.: ``Art. 414. \\n (( (Persone che...). )) \\n ...``
          3. Senza rubrica:  ``Art. N. \\n testo...``
        """
        del article_num  # reserved for future disambiguation
        cleaned = text.strip()

        # 1. Rimuovi header "Art. N."
        header_match = _ART_HEADER_RE.match(cleaned)
        if header_match:
            cleaned = cleaned[header_match.end() :]
        cleaned = cleaned.lstrip()

        # 2. Rubrica tra doppie parentesi (modificata)
        if cleaned.startswith("(("):
            m = _RUBRICA_MOD_RE.match(cleaned)
            if m:
                rubrica = self._cleanup_rubrica(m.group(1))
                body = cleaned[m.end() :].lstrip()
                return rubrica, self._clean_markers(body)

        # 3. Rubrica con parentesi singole. Le parentesi sono un segnale
        #    forte, quindi usiamo il filtro permissivo (ammette punti interni
        #    come "Concorso formale. Reato continuato").
        m = _RUBRICA_STD_RE.match(cleaned)
        if m:
            rubrica_raw = m.group(1).strip()
            if self._looks_like_rubrica(rubrica_raw, strict=False):
                body = cleaned[m.end() :].lstrip()
                return self._cleanup_rubrica(rubrica_raw), self._clean_markers(body)

        # 4. Rubrica "plain": prima riga/paragrafo dopo header, senza parentesi,
        #    separata da blank line dal corpo. (Es. CP art. 416-bis.)
        #    Filtro strict per evitare che un comma unico del corpo venga scambiato
        #    per una rubrica quando il testo è breve.
        parts = re.split(r"\n\s*\n", cleaned, maxsplit=1)
        if len(parts) == 2:
            first_block = parts[0].strip()
            rest = parts[1]
            if self._looks_like_rubrica(first_block, strict=True):
                return self._cleanup_rubrica(first_block), self._clean_markers(rest)

        # 5. Nessuna rubrica identificabile
        return None, self._clean_markers(cleaned)

    @staticmethod
    def _looks_like_rubrica(candidate: str, *, strict: bool = True) -> bool:
        """Euristica: una rubrica è breve e nominale.

        - strict=True: nessun punto interno (usato per rubriche "plain" senza
          parentesi — serve a evitare falsi positivi sui commi del corpo).
        - strict=False: ammette punti interni (usato per rubriche tra
          parentesi, il cui wrapping è già un segnale forte).
        """
        if not candidate or len(candidate) > 160:
            return False
        if strict and candidate.count(".") > 0:
            return False
        words = candidate.split()
        if not words or len(words) > 15:
            return False
        lower = candidate.lower()
        bad_markers = ("chiunque ", "qualunque ", "è punito", "e' punito", "salvo che")
        return not any(b in lower for b in bad_markers)

    @staticmethod
    def _cleanup_rubrica(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def _clean_markers(self, text: str) -> str:
        """Pulisce marcatori `(( ... ))` e whitespace ridondante."""
        if not self._keep_markers:
            # Le doppie parentesi `(( ... ))` indicano passaggi introdotti da
            # modifica successiva ma vigenti. Preserviamo il contenuto, togliamo
            # le parentesi (e i numeri di nota tipo `((3))`).
            text = re.sub(r"\(\(\s*([0-9]+)\s*\)\)", "", text)  # ((3)) note refs
            text = re.sub(r"\(\(\s*", "", text)
            text = re.sub(r"\s*\)\)", "", text)
        # Normalizza whitespace: singoli newline in spazio, doppi newline preservati
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ------------------------------------------------------------------
    # Comma/letter splitting
    # ------------------------------------------------------------------

    def _split_commi(self, body: str) -> list[CanonicalComma]:
        """Divide il corpo dell'articolo in commi.

        Strategia:
        1. Se ci sono pattern numerati "1.", "2.", "1-bis." all'inizio di blocchi,
           usali come separatori (affidabile).
        2. Altrimenti, dividi sui paragrafi separati da blank line (`\n\n`) e
           numera progressivamente (1, 2, 3, ...).
        3. Se il testo è un singolo paragrafo senza numerazione, è un comma unico "1".
        """
        body = body.strip()
        if not body:
            return []

        # Strategy 1: numerazione esplicita
        matches = list(_COMMA_NUM_RE.finditer(body))
        if len(matches) >= 2:
            # Verifica che inizi davvero da "1." per evitare falsi positivi
            # (es. testi che contengono "17." come riferimento)
            first_num = matches[0].group(1).lower()
            if first_num.startswith("1") or first_num == "1-bis":
                return self._commi_from_matches(body, matches)

        # Strategy 2: split per paragrafo doppio-newline
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if len(paragraphs) > 1:
            return [
                CanonicalComma(
                    number=str(i + 1),
                    text=para,
                    letters=self._extract_letters(para),
                )
                for i, para in enumerate(paragraphs)
            ]

        # Strategy 3: comma unico
        return [
            CanonicalComma(
                number="1",
                text=body,
                letters=self._extract_letters(body),
            )
        ]

    def _commi_from_matches(
        self, body: str, matches: list[re.Match[str]]
    ) -> list[CanonicalComma]:
        commi: list[CanonicalComma] = []
        for i, m in enumerate(matches):
            number = m.group(1).strip().lower().replace(" ", "-")
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            text = body[start:end].strip()
            if text:
                commi.append(
                    CanonicalComma(
                        number=number,
                        text=text,
                        letters=self._extract_letters(text),
                    )
                )
        return commi

    @staticmethod
    def _extract_letters(text: str) -> list[CanonicalCommaLetter] | None:
        matches = list(_LETTER_RE.finditer(text))
        if len(matches) < 2:
            return None
        letters: list[CanonicalCommaLetter] = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            letters.append(
                CanonicalCommaLetter(letter=m.group(1).lower(), text=text[start:end].strip())
            )
        return letters
