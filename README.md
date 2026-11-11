# Disaster Recovery Lab

A reproducible PostgreSQL recovery laboratory with failure injection, logical backups, clean-room restores, integrity checks, and measured recovery objectives.

## Run locally

Requires Python 3.10+ and a running Docker engine. No Python packages, cloud account, database credentials, or published ports are needed. Uses disposable containers with synthetic data and PostgreSQL 17. Allow roughly 1 GB of available memory.

```sh
python3 -m unittest discover -s tests -v
python3 lab.py data-loss
python3 lab.py service-loss
python3 lab.py corrupt-backup
```

Run commands from the repository root. Each invocation creates a unique evidence directory under `artifacts/`. Containers use a private, generated password, no container networking, and temporary database storage. Only containers created by that invocation are removed. No existing database URL or container name is accepted.

## Scenarios

| Drill | Injected failure | Success criteria |
| --- | --- | --- |
| `data-loss` | Delete all rows after taking a backup | Restore into a new container; exact baseline matches; write probe passes |
| `service-loss` | Remove the source container and its temporary data | Recreate PostgreSQL and restore the independent logical backup |
| `corrupt-backup` | Truncate the archive | Checksum mismatch is detected before restoration; no recovery objective is evaluated |

Both recovery drills intentionally commit one row **after** the backup. Verification confirms that this row is lost, making the limitation of periodic snapshots visible.

## Recovery flow

1. Pull the image and start a disposable source database.
2. Seed 100 deterministic rows and record the sorted baseline.
3. Create a custom-format `pg_dump` archive and independent SHA-256 checksum.
4. Commit a post-backup transaction and inject the selected failure.
5. Start a fresh recovery database, verify the archive checksum, and use `pg_restore` with fail-fast transactional restoration.
6. Compare every recovered row and payload to the baseline, verify the expected lost row, and execute a database write probe.
7. Write `report.json` and remove the lab containers, including after a failed drill.

## RTO / RPO definitions

**Measured recovery time:** monotonic elapsed time from immediately before failure injection until restore, content verification, and the database write probe finish. Includes fresh recovery-container initialization. Excludes initial image download, backup creation, human detection/approval, application reconnection, DNS, and traffic cutover. It is a database-level drill measurement, not an end-to-end service RTO.

**Recovery point age:** elapsed time from immediately before the backup starts until failure injection begins. There are no concurrent writers during the dump. This conservative age is compared with the configurable RPO target; the intentionally missing post-backup row is reported separately as `lost_rows: 1`.

Default lab targets: RTO 120 seconds and RPO 60 seconds. These are demonstration thresholds, not production promises. Breaching either target exits nonzero even when the restore itself is correct.

```sh
python3 lab.py service-loss --rto-target 180 --rpo-target 90
```

Each report contains the scenario, resolved image ID, outcome, measured values, targets, and any failure. Successful recovery reports also contain archive/data checksums and verification outcomes. No benchmark numbers are claimed before an actual run.

## CI verification

[Recovery drills](.github/workflows/recovery.yml) runs the three scenarios independently on pushes, pull requests, and manual dispatch. It runs the unit checks first and uploads JSON evidence even when a drill fails. Raw database dumps remain local and are not uploaded as CI artifacts.

Local validation during initial authoring: six unit tests and Python compilation passed. Docker was unavailable on the authoring machine; end-to-end restore results must be verified in GitHub Actions or a Docker-enabled environment. A workflow file alone is not evidence that drills passed.

## Operator runbook

For a real incident, adapt the steps to the actual service:

1. Record impact, incident start, last good transaction, and recovery objectives. Stop harmful writes and preserve evidence.
2. Identify a backup from before the destructive event and verify its provenance, integrity, and decryptability. A checksum detects byte changes; it does not establish backup trust or semantic correctness.
3. Restore into an isolated target; keep the damaged source available for investigation.
4. Validate schema, constraints, representative business queries, data completeness, credentials, and application compatibility.
5. Measure the actual data gap. Obtain the required operational approval before reconnecting applications or promoting the target.
6. Monitor traffic and errors, reconcile missing transactions, and document elapsed time, data loss, and follow-up actions.

The executable lab automates steps on its synthetic database only. It does not execute cloud failover, production promotion, or application cutover.

## Design decisions and limitations

- Logical backups keep the exercise small and portable. This is not PITR: no WAL archiving, physical backups, replicas, or regional failover are configured.
- A fresh restore target avoids overwriting a damaged source. The service-loss drill explicitly removes only its own disposable source.
- The checksum is stored separately from the dump; both are on the same host. This is not an immutable, encrypted, offsite backup design.
- The fixture is tiny and quiescent during backup. Production datasets, concurrent workloads, roles, extensions, and external dependencies need additional validation.
- `postgres:17` floats across patch releases. Reports capture the resolved local image ID; use `--image postgres@sha256:<approved-digest>` for a fixed image.
- Cleanup is best effort. A forced process termination may leave uniquely named containers labeled `dr-lab=true`; inspect those containers before removing them.
- CI does not prove business continuity, production capacity, or regulatory compliance.

## Portfolio extensions

Next iterations could add pgBackRest and WAL-based PITR, encrypted offsite storage, restore-time benchmarks at different dataset sizes, application smoke tests, and a regional recovery tabletop. Keep measured evidence separate from hypothetical designs.

For AI-assisted runbook and workflow reviews, see [AI DevOps Prompts](https://github.com/yoaoxd/ai-devops-prompts). AI suggestions do not establish a successful recovery; verified restores do.

## References

- [PostgreSQL 17 pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
- [PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)
- [PostgreSQL backup and restore](https://www.postgresql.org/docs/17/backup.html)
