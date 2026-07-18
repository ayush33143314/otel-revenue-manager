# Deployment

Live agent (AWS App Runner, us-east-1, colocated with RDS):

- **URL:** https://azfppawb3r.us-east-1.awsapprunner.com
- **Auth:** HTTP basic auth (username `gm-review`; password sent privately via
  the submission intake channel — never committed).
- **Health:** `GET /health` → `db_fingerprint`, `dataset_revision`, `row_hash`,
  `financial_status_posted_only_rows`, read live from RDS; matches
  `etl/LOAD_PROOF.json`.

## Topology

```
browser ──HTTPS──► App Runner (FastAPI + UI + agent)
                      ├─ secrets at boot ─► Secrets Manager (otel/revenue-agent)
                      ├─ reads reservation data / stores chat memory ─► RDS Postgres
                      └─ model ─► Anthropic API
```

The container is app-only (no Playwright). It **reads** the database; it never
scrapes. The reservation data is loaded by the local ETL; agent conversation
memory (checkpointer/store tables) is created automatically on first boot.

## AWS resources

| Resource | Name / ARN |
|----------|------------|
| App Runner service | `otel-revenue-agent` (`arn:…:service/otel-revenue-agent/73b6340088f54622a98a3204c4a09ab3`) |
| ECR image | `741339852886.dkr.ecr.us-east-1.amazonaws.com/otel-revenue-agent:latest` |
| RDS Postgres | `otel-revenue-db` |
| Secrets Manager | `otel/revenue-agent` (APP_SECRETS_JSON: ANTHROPIC_API_KEY, DATABASE_URL, BASIC_AUTH_USER, BASIC_AUTH_PASS) |
| IAM roles | `otel-apprunner-ecr` (pull image), `otel-apprunner-instance` (read secret) |

Secrets are injected as one JSON blob (`APP_SECRETS_JSON`) via the instance
role; `app/config.py` unpacks it into env vars at startup. No secret is in git.

## Redeploy (after a code change)

```bash
docker buildx build --platform linux/amd64 -t otel-revenue-agent:latest --load .
docker tag  otel-revenue-agent:latest 741339852886.dkr.ecr.us-east-1.amazonaws.com/otel-revenue-agent:latest
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 741339852886.dkr.ecr.us-east-1.amazonaws.com
docker push 741339852886.dkr.ecr.us-east-1.amazonaws.com/otel-revenue-agent:latest
aws apprunner start-deployment --service-arn <service ARN> --region us-east-1
```

## Submission-day data refresh (same calendar day)

```bash
DATABASE_URL="<RDS url>" ./scripts/load_hosted_db.sh --scrape   # scrape → load RDS → reconcile → proofs
git add etl/SCRAPE_MANIFEST.json etl/LOAD_PROOF.json && git commit -m "Refresh load proofs"
curl -s https://azfppawb3r.us-east-1.awsapprunner.com/health     # confirm fingerprint matches the fresh proof
```
