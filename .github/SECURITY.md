# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting ("Report a vulnerability" in the
Security tab) once the repository is public. Until a dedicated address is
announced, that is the only channel.

Please include: affected component (api / web / ingestion / rag-core),
reproduction steps, impact assessment. You will receive an acknowledgement
within 72 hours.

## Scope notes

- Caucus processes **public legal texts**; a default deployment holds no
  personal data. Deployments that add user accounts/conversations must do
  their own DPIA.
- The reference deployment sends queries to third-party LLM providers
  (OpenAI by default). Self-hosted backends are supported and recommended for
  privileged content — see the configuration in `.env.example`.
- Cassazione decisions are ingested exclusively in the official anonymized
  form published by SentenzeWeb; the harvester discards documents still
  "in fase di oscuramento". Report any de-anonymization vector as a
  vulnerability.

## Supported versions

Pre-1.0: only the `main` branch receives fixes.
