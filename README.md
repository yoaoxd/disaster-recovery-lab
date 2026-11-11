# Disaster Recovery Lab

**Can you restore your PostgreSQL backup after the database disappears?**

Practice three failure scenarios with Python and Docker: delete data, lose the database container, or corrupt a backup. Restore into a fresh database, verify every baseline row, and collect a JSON recovery report.

Built for Platform Engineers, SREs, and developers learning to test recovery procedures. No cloud account or Python dependencies required.

## Quick start

Requires Git, Python 3.10+, and a running Docker engine. Allow roughly 1 GB of available memory and network access to pull PostgreSQL 17.

```sh
git clone https://github.com/yoaoxd/disaster-recovery-lab.git
cd disaster-recovery-lab
python3 -m unittest -v test_lab
python3 lab.py service-loss
```

The drill seeds 100 rows, takes a backup, writes one additional row, removes its own source container, and restores into a new container. A successful run prints `"status": "passed"`, verifies 100 restored rows, reports `"lost_rows": 1`, and passes a write probe. Actual timings depend on your machine; the default targets are demonstration thresholds.

Look for the `Evidence:` path at the end of the output. Each run saves `report.json`, `backup.dump`, and `backup.sha256` under a unique `artifacts/` directory. Exit code 0 means the scenario passed; exit code 1 means an error or a missed recovery target.

## Choose a drill

| Command | Failure | What it checks |
| --- | --- | --- |
| `python3 lab.py data-loss` | Delete all rows after backup | Fresh restore matches the baseline and accepts writes |
| `python3 lab.py service-loss` | Remove the source container and temporary data | Independent backup can rebuild the database |
| `python3 lab.py corrupt-backup` | Truncate the backup archive | Checksum validation refuses the damaged archive |

Both recovery drills intentionally lose the transaction written after the backup. The corruption drill passes when corruption is detected; it does not perform a restore or evaluate recovery objectives.

## Recovery flow

1. Pull the image and start a disposable source database.
2. Seed 100 deterministic rows and record a sorted baseline.
3. Create a custom-format `pg_dump` archive and a separate SHA-256 checksum.
4. Commit a post-backup transaction and inject the failure.
5. Start a fresh database, verify the archive, and restore with `pg_restore --exit-on-error --single-transaction`.
6. Compare every recovered row and payload, verify the expected missing row, and run a write probe.
7. Save the report and clean up the lab containers.

## Read the evidence

| Field | Meaning |
| --- | --- |
| `status` | Scenario passed or failed |
| `image_id` | Resolved local image used for the run |
| `recovery_seconds` | Failure injection through restore, verification, and write probe |
| `recovery_point_age_seconds` | Time from backup start to failure injection |
| `objectives_met` | Both configured time targets were met |
| `restored_rows` / `lost_rows` | Baseline restored and intentionally missing post-backup row |
| `backup_sha256` / `data_sha256` | Archive and recovered baseline fingerprints |
| `error` | Failure detail, when available |

Recovery-only fields are absent from the corruption scenario. If you share results, include the scenario, image ID, OS/architecture, Docker version, available resources, and report. Compare like-for-like runs rather than treating a tiny fixture as a production benchmark.

## RTO and RPO boundaries

**Measured recovery time** includes failure injection, fresh recovery-container initialization, restoration, content verification, and the write probe. It excludes initial image download, backup creation, human detection/approval, application reconnection, DNS, and traffic cutover. This measures database recovery, not end-to-end service RTO.

**Recovery point age** starts immediately before the backup and ends at failure injection. The fixture has no concurrent writers during the dump. This conservative age is compared with the RPO target; `lost_rows: 1` separately records the deliberate post-backup data loss.

Defaults: RTO 120 seconds, RPO 60 seconds. Breaching either target exits nonzero even if restoration is correct.

```sh
python3 lab.py service-loss --rto-target 180 --rpo-target 90
```

## Isolation and cleanup

The lab accepts no existing database URL or container name. It uses synthetic data, generated container names and passwords, `--network none`, no published ports, and temporary database storage. Cleanup targets only containers created by that invocation. Local evidence files remain available afterward.

Cleanup is best effort. After a forced termination, inspect containers labeled `dr-lab=true` before removing any leftovers. Never adapt the destructive commands to a production database without an independently reviewed recovery plan.

## Troubleshooting

- **Docker command missing or daemon unavailable:** start/install your Docker engine and check `docker info` before rerunning.
- **Image pull fails:** check network access to the registry and available disk space. The initial image pull happens outside the recovery timer.
- **Readiness timeout:** check Docker resources; PostgreSQL has a 60-second readiness window.
- **Restore succeeds but status fails:** inspect `objectives_met` and measured times. Adjust targets deliberately, keeping the original report for comparison.
- **Unit tests pass but the drill fails:** the six unit tests validate helper contracts; they do not exercise Docker or PostgreSQL restoration.

## Validation status

Run `python3 -m unittest -v test_lab` for the six unit checks and run each scenario on a Docker-enabled machine for end-to-end evidence. This repository currently has no recovery CI workflow; a passing restore must be established from an actual run and its report. No measured performance claims are published here.

## Operator runbook

For a real incident, adapt the procedure to the service:

1. Record impact, incident start, last good transaction, and recovery objectives. Stop harmful writes and preserve evidence.
2. Select a backup from before the destructive event. Verify provenance, integrity, and decryptability. A checksum alone does not prove trust or semantic correctness.
3. Restore into an isolated target and preserve the damaged source for investigation.
4. Validate schema, constraints, business queries, completeness, credentials, and application compatibility.
5. Measure the data gap and obtain operational approval before application cutover.
6. Monitor the recovered service, reconcile missing transactions, and document follow-up work.

## Scope and next experiments

This is a small logical-backup lab. It does not implement WAL-based PITR, physical backups, replicas, regional failover, encrypted offsite storage, or application cutover. Backups and checksums live on the same host. Production datasets, concurrent workloads, roles, extensions, and external dependencies need additional validation.

`postgres:17` floats across patch releases. For repeatable image selection, use `--image postgres@sha256:<approved-digest>` and retain the reported image ID.

Useful next contributions:

- Recovery CI with downloadable JSON evidence.
- A WAL/PITR scenario that demonstrates recovering the post-backup transaction.
- Larger deterministic datasets and comparable recovery reports.
- Application smoke tests after restoration.

## Try it, improve it, share it

Found a failure? [Open an issue](https://github.com/yoaoxd/disaster-recovery-lab/issues) with the command, environment, and sanitized report. Small reproducibility fixes and documented drill results are welcome. Do not upload credentials or real database dumps.

If this lab helps you practice recovery or teach your team, consider starring it so you can find it again and sharing it with another engineer who owns backups.

## References

- [PostgreSQL 17 pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
- [PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)
- [PostgreSQL backup and restore](https://www.postgresql.org/docs/17/backup.html)
