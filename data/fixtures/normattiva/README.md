# Fixture AKN Normattiva

Snapshot Akoma Ntoso XML scaricati da `normattiva.it` per test offline del parser.

| File | Fonte | URN | Dimensione |
|------|-------|-----|------------|
| `codice_civile_20260417.akn.xml` | Normattiva | `urn:nir:stato:regio.decreto:1942-03-16;262` | ~10 MB |
| `codice_penale_20260417.akn.xml` | Normattiva | `urn:nir:stato:regio.decreto:1930-10-19;1398` | ~4 MB |

Testo di legge italiano = pubblico dominio (Berne Convention art. 2(4) + L. 633/1941 art. 5). Normattiva è rilasciato dall'Istituto Poligrafico e Zecca dello Stato per uso libero.

## Come rigenerare

```bash
python -m avvocato_ingestion.cli fetch --codice cc --output data/fixtures/normattiva/
python -m avvocato_ingestion.cli fetch --codice cp --output data/fixtures/normattiva/
```

Vedi `services/ingestion/src/avvocato_ingestion/parsers/normattiva_akn.py`.
