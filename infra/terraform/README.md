# Terraform (riferimento PARZIALE, non deployabile as-is)

> ⚠️ **STATO (2026-07-31)**: questo modulo è un **riferimento incompleto**,
> non un deploy funzionante, e non è mai stato applicato end-to-end.
> Mancano almeno: il vector store (Qdrant non è nel modulo: senza di esso il
> RAG non parte), `google_sql_user`, le `google_secret_manager_secret`, una
> service account dedicata per il servizio web, il backend GCS per lo state e
> l'ingress ristretto. Da trattare come traccia architetturale.
>
> Per provare Caucus usa lo stack locale (`make up`): è quello testato.
> Un deploy di riferimento completo è in roadmap.

Stack minimale per `avvocato-dev` e `avvocato-prod`, regione `europe-west1`.

## Risorse create

- VPC dedicata + subnet + Serverless VPC Connector (per Cloud Run → Cloud SQL/Redis private)
- Cloud SQL Postgres 16 con `pgvector` abilitato, backup + PITR
- Memorystore Redis 7 (BASIC in dev, STANDARD_HA in prod)
- Artifact Registry (Docker)
- Cloud Run v2 service `api` + `web`
- Service account dedicati con IAM minimo
- GCS bucket `documents` (tenant data) e `sources` (snapshot normativi)

## Fuori scope Fase 1 (aggiungere quando serve)

- Qdrant: per ora dev → `qdrant/qdrant` su docker-compose; prod → StatefulSet GKE (vedi `infra/k8s/`)
- Langfuse: stesso pattern (self-host su Cloud Run o GKE a seconda del carico)
- Vertex AI: nessuna risorsa Terraform; accesso via IAM + API già attivata
- WorkOS / Clerk: config applicativa, non infra

## Uso

```bash
cd infra/terraform
cp dev.tfvars.example dev.tfvars
terraform init
terraform plan  -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

Per prod, creare un progetto GCP separato (`avvocato-prod`) e usare un backend GCS remoto per lo state.
