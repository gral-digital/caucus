"""Parser per fonti normative.

Attualmente solo Normattiva è supportato (via AKN XML). Altre fonti
(Gazzetta Ufficiale, Cassazione) avranno parser separati in questo modulo.
"""

from avvocato_ingestion.parsers.normattiva_akn import (
    CODICI_CATALOG,
    CodiceInfo,
    NormattivaAknParser,
)

__all__ = ["NormattivaAknParser", "CodiceInfo", "CODICI_CATALOG"]
