# 📜 Standards Drift Wire

An autonomous, zero-maintenance data infrastructure running on GitHub Actions. It parses the official IETF RFC index to detect and ledger protocol obsoletions, status transitions, and standard updates.

## Data Feeds for Agents
Optimized for AI codegen pipelines, compliance checkers, and networking bots.

- [`v1/recent-standards.json`](public/v1/recent-standards.json)
- [`v1/obsoleted.json`](public/v1/obsoleted.json)
- [`llms.txt`](public/llms.txt)
- `standards.parquet` (Columnar database snapshot)

## Architecture
- **Ingest**: Official RFC Editor XML Index (`rfc-index.xml`)
- **Database**: DuckDB (cached ephemerally)
- **Ledger**: Git-native append-only JSONL committed to `/data/history`
- **Delivery**: GitHub Pages (Fastly CDN)
