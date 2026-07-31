# Data Model

> ⚠️ **STATO (2026-07-31)**: lo schema reale è la somma delle migration
> Alembic (`apps/api/alembic/versions/`) — oggi: norm_source, norm_partition,
> norm_comma, norm_citation (con target denormalizzato), norm_chunk,
> case_law, case_law_chunk. Non ancora implementati rispetto a quanto sotto:
> versioning multivigenza con chiusura effective_to, path ltree nativo
> (oggi VARCHAR+trigram), tabelle applicative (utenti/conversazioni/audit).

Modello dati della gerarchia normativa italiana. Il modello è progettato per preservare la struttura giuridica (gerarchia di partizioni) e per supportare citazioni machine-readable riusabili su tutti i moduli.

## 1. Fonti e tassonomia

| Fonte | Tipo | Aggiornamento | Parsing |
|-------|------|---------------|---------|
| Normattiva (Portale della normativa italiana) | `codici`, `leggi`, `d.lgs`, `d.l.`, `d.p.r.` | settimanale / evento | XML AkomaNtoso (quando disponibile) o HTML |
| Gazzetta Ufficiale | `atti di pubblicazione` | quotidiano | HTML + PDF |
| italgiure.giustizia.it | `sentenze Cassazione` | quasi-quotidiano | HTML + PDF |
| CED Cassazione (massimario) | `massime` | mensile | JSON / XML |
| Codici deontologici (CNF) | `norme deontologiche` | raro | PDF |

## 2. Gerarchia partizioni (Codice Civile / Penale)

La struttura segue la terminologia normativa italiana:

```
Codice
└── Libro (I, II, III, IV, V, VI)
    └── Titolo (Titolo I, II, …)
        └── Capo (Capo I, II, …)
            └── Sezione (opzionale)
                └── Articolo (art. 2043)
                    └── Comma (comma 1, 2, …)
                        └── Lettera (opzionale: a), b), …)
                            └── Numero (opzionale: 1), 2), …)
```

Il Codice Penale ha la stessa struttura ma non sempre `Sezione` (più raro). Altre leggi possono avere struttura diversa — il modello è volutamente flessibile.

## 3. Entità principali

### `norm_source`
Fonte normativa root (un codice, una legge, un d.lgs.).

| Campo | Tipo | Note |
|-------|------|------|
| id | uuid | PK |
| urn | text UNIQUE | URN normativa es. `urn:nir:stato:codice.civile` |
| short_id | text UNIQUE | es. `cc`, `cp`, `dlgs-231-2001` |
| title | text | "Codice Civile" |
| type | enum | `codice`, `legge`, `dlgs`, `dl`, `dpr`, `cost`, `tue`, `tfue`, `reg-ue`, `dir-ue`, `deont` |
| issued_at | date | Data emanazione |
| in_force_from | date | |
| in_force_to | date | NULL se in vigore |
| source_url | text | |
| source_hash | text | SHA-256 dell'ultimo snapshot |
| metadata | jsonb | libero |

### `norm_partition`
Nodo della gerarchia (libro, titolo, capo, sezione, articolo). Tabella unica con `kind` + `parent_id` → alberi materializzati.

| Campo | Tipo | Note |
|-------|------|------|
| id | uuid | PK |
| source_id | uuid | FK norm_source |
| parent_id | uuid NULL | FK self |
| kind | enum | `libro`, `titolo`, `capo`, `sezione`, `articolo`, `disposizione-transitoria` |
| number | text | "I", "2043", "bis" preservato |
| label | text | "Libro IV — Delle obbligazioni" |
| ordinal | int | Per ordinamento |
| path | ltree | `cc.libro_iv.titolo_ix.capo_i.art_2043` (indice veloce) |
| citation | text | Forma canonica `art. 2043 c.c.` |
| rubrica | text | Titoletto dell'articolo se presente |
| full_text | text | Testo completo (solo per `articolo` / partizioni foglia) |
| effective_from | date | Primo giorno di vigore del testo corrente |
| effective_to | date NULL | Per versioning |
| metadata | jsonb | |

### `norm_comma`
Commi sono entità separate per permettere citazioni e vettorializzazione granulari.

| Campo | Tipo | Note |
|-------|------|------|
| id | uuid | PK |
| partition_id | uuid | FK norm_partition (kind=articolo) |
| ordinal | int | 1, 2, 3, … |
| number | text | "1", "1-bis", "2" |
| text | text | Testo del comma |
| letters | jsonb | `[{"letter":"a","text":"..."}]` per liste |
| effective_from | date | |
| effective_to | date NULL | |

### `norm_citation`
Citazioni estratte automaticamente dal testo (riferimenti incrociati).

| Campo | Tipo | Note |
|-------|------|------|
| id | uuid | PK |
| from_partition_id | uuid | Articolo che cita |
| from_comma_id | uuid NULL | Comma specifico |
| to_partition_id | uuid NULL | Articolo citato (se risolvibile) |
| to_source_id | uuid | FK norm_source |
| raw_text | text | Testo grezzo della citazione |
| citation_kind | enum | `richiamo`, `modifica`, `abrogazione`, `rinvio` |
| confidence | float | 0-1 dal parser |

### `norm_chunk`
Unità di indicizzazione (stored in Postgres + mirrored in Qdrant).

| Campo | Tipo | Note |
|-------|------|------|
| id | uuid | PK |
| partition_id | uuid | |
| comma_id | uuid NULL | |
| chunk_kind | enum | `articolo-full`, `comma`, `rubrica`, `window` (sliding) |
| text | text | |
| text_tsv | tsvector | FTS italiano `to_tsvector('italian', unaccent(text))` |
| embedding | vector(1024) | bge-m3 dense |
| sparse_embedding | jsonb | bge-m3 sparse (stored also in Qdrant) |
| token_count | int | |
| qdrant_point_id | uuid | Stesso ID usato in Qdrant |
| metadata | jsonb | es. `{"codice":"cc","articolo":"2043"}` |

### `case_law` (fase 4)
Sentenze (Cassazione principalmente, ma estendibile a merito).

| Campo | Tipo | Note |
|-------|------|------|
| id | uuid | PK |
| court | enum | `cass-civ`, `cass-pen`, `cost`, `app`, `trib`, `giudice-pace` |
| section | text | "sez. III", "sezioni unite" |
| decision_number | text | |
| decision_year | int | |
| decided_at | date | |
| published_at | date | |
| parties_hashed | text | Privacy: hash dei nomi per dedup, non display |
| matter | text[] | Materie (lista tag) |
| normative_refs | uuid[] | FK norm_partition[] |
| massima | text | |
| full_text | text | |
| outcome | enum | `accolto`, `rigettato`, `inammissibile`, `cassato-rinvio`, … |
| source_url | text | |

### `case_law_chunk`
Analogo a `norm_chunk` per sentenze.

### `tenant`, `user`, `conversation`, `message`, `document` (fase 2+)
Modelli standard multi-tenant con RLS. Specifica in `docs/MULTITENANCY.md` (TODO).

## 4. Citazioni machine-readable

Forma canonica usata da LLM, UI, API:

```
<cite src="cc" part="art" num="2043" comma="1" />
<cite src="cp" part="art" num="575" />
<cite src="cass-civ" decision="12345/2024" />
```

In risposta LLM → parser frontend le trasforma in link cliccabili:

```html
<a href="/norma/cc/art/2043#c1" data-cite="cc:art:2043:1">art. 2043, c. 1 c.c.</a>
```

Schema JSON formale in `data/schemas/citation.schema.json`.

## 5. Versioning normativo

Le norme cambiano. Ogni `norm_partition` e `norm_comma` ha `effective_from` / `effective_to`. Una query "stato vigente al 2023-06-01" filtra via:

```sql
WHERE effective_from <= '2023-06-01'
  AND (effective_to IS NULL OR effective_to > '2023-06-01')
```

Ogni modifica normativa crea nuove righe (insert-only append, nessun UPDATE distruttivo). Lo storico permette di rispondere "cosa diceva l'art. X al momento Y".

## 6. Indici critici (Postgres)

```sql
CREATE INDEX ON norm_partition USING gist(path);                          -- ltree
CREATE INDEX ON norm_partition (source_id, kind, number);
CREATE INDEX ON norm_chunk USING gin(text_tsv);                           -- FTS italiano
CREATE INDEX ON norm_chunk USING ivfflat(embedding vector_cosine_ops);    -- ANN (upgrade a HNSW quando pgvector ≥0.7 lo permette senza tradeoff)
CREATE INDEX ON norm_citation (from_partition_id);
CREATE INDEX ON norm_citation (to_partition_id);
CREATE INDEX ON case_law USING gin(normative_refs);
```

FTS italiana richiede la config `italian` e l'estensione `unaccent`. Entrambe si configurano nella migration iniziale.

## 7. Qdrant payload schema

Ogni point in Qdrant ha lo stesso UUID del corrispondente `norm_chunk.id` (così una volta fatto il retrieval top-k da Qdrant, fai un singolo `SELECT … WHERE id = ANY(...)` in Postgres per hydratare).

Payload:
```json
{
  "source": "cc",
  "kind": "comma",
  "partition_id": "uuid",
  "articolo": "2043",
  "comma": "1",
  "path": "cc.libro_iv.titolo_ix.capo_i.art_2043",
  "effective_from": "1942-04-16",
  "effective_to": null,
  "token_count": 128
}
```

Collection: una per corpus (`codici`, `leggi_speciali`, `cassazione`, `tenant_<id>_docs`).
