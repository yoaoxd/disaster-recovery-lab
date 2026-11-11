#!/usr/bin/env python3
"""Disposable PostgreSQL recovery drills. Python standard library + Docker."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import secrets
import subprocess
import time
import uuid


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_archive(data, expected):
    if digest(data) != expected:
        raise ValueError('Backup checksum mismatch; restore refused')


def metrics(elapsed, age, lost, rto_target, rpo_target):
    return dict(recovery_seconds=round(elapsed, 3),
                recovery_point_age_seconds=round(age, 3), lost_rows=lost,
                rto_target_seconds=rto_target, rpo_target_seconds=rpo_target,
                objectives_met=elapsed <= rto_target and age <= rpo_target)


class Drill:
    def __init__(self, image):
        self.prefix = 'dr-lab-' + uuid.uuid4().hex[:12]
        self.image = image
        self.created = []
        self.password = secrets.token_hex(24)

    def docker(self, *args, data=None, timeout=120):
        result = subprocess.run(['docker', *args], input=data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout

    def start(self, role):
        name = self.prefix + '-' + role
        self.docker('run', '-d', '--name', name, '--label', 'dr-lab=true',
                    '--network', 'none', '--tmpfs', '/var/lib/postgresql/data',
                    '-e', 'POSTGRES_PASSWORD=' + self.password,
                    '-e', 'POSTGRES_DB=lab', self.image)
        self.created.append(name)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                self.sql(name, 'SELECT 1;')
                return name
            except RuntimeError:
                time.sleep(0.5)
        raise RuntimeError('PostgreSQL readiness timed out')

    def sql(self, name, query):
        return self.docker('exec', '-i', name, 'psql', '-X', '-qAt',
                           '-v', 'ON_ERROR_STOP=1', '-h', '127.0.0.1',
                           '-U', 'postgres', '-d', 'lab',
                           data=query.encode()).decode().strip()

    def snapshot(self, name):
        return self.sql(name, "SELECT id, payload FROM events ORDER BY id;").encode()

    def cleanup(self):
        for name in reversed(self.created):
            try:
                subprocess.run(['docker', 'rm', '-fv', name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                print('Cleanup incomplete; inspect lab container:', name)


def run(args):
    out = Path(args.output) / (args.scenario + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    drill = Drill(args.image)
    report = dict(scenario=args.scenario, image=args.image, status='failed')
    try:
        # Pull before the outage timer. Image download is a recovery prerequisite.
        drill.docker('pull', args.image, timeout=300)
        report['image_id'] = drill.docker('image', 'inspect', args.image,
                                         '--format', '{{.Id}}').decode().strip()
        source = drill.start('source')
        drill.sql(source, "CREATE TABLE events(id integer PRIMARY KEY, payload text NOT NULL);"
                  "INSERT INTO events SELECT i, 'order-' || i FROM generate_series(1,100) i;")
        baseline = drill.snapshot(source)
        # No concurrent writers in this fixture; timestamp conservatively precedes dump.
        point = time.monotonic()
        backup = drill.docker('exec', source, 'pg_dump', '-U', 'postgres',
                              '-d', 'lab', '-Fc', '--no-owner', '--no-acl')
        backup_path = out / 'backup.dump'
        backup_path.write_bytes(backup)
        checksum = digest(backup)
        (out / 'backup.sha256').write_text(checksum + '\n')
        drill.sql(source, "INSERT INTO events VALUES (101, 'after-backup');")
        if args.scenario == 'corrupt-backup':
            backup_path.write_bytes(backup[:32])
            try:
                check_archive(backup_path.read_bytes(), checksum)
            except ValueError:
                report.update(status='passed', corruption_detected=True,
                              restored=False, objectives_evaluated=False)
            else:
                raise RuntimeError('Corrupt backup was accepted')
        else:
            outage = time.monotonic()
            age = outage - point
            if args.scenario == 'data-loss':
                drill.sql(source, 'DELETE FROM events;')
                if drill.snapshot(source):
                    raise RuntimeError('Failure injection did not delete data')
            else:
                drill.docker('rm', '-fv', source)
                drill.created.remove(source)
            recovered = drill.start('recovered')
            check_archive(backup_path.read_bytes(), checksum)
            drill.docker('exec', '-i', recovered, 'pg_restore', '-U', 'postgres',
                         '-d', 'lab', '--exit-on-error', '--single-transaction',
                         '--no-owner', '--no-acl', data=backup_path.read_bytes())
            actual = drill.snapshot(recovered)
            if actual != baseline:
                raise RuntimeError('Restored data does not match backup baseline')
            if drill.sql(recovered, 'SELECT count(*) FROM events WHERE id=101;') != '0':
                raise RuntimeError('Unexpected post-backup row')
            # A write/read probe establishes database usability after restore.
            probe = drill.sql(recovered,
                              "INSERT INTO events VALUES (102,'probe') RETURNING payload;")
            if probe != 'probe':
                raise RuntimeError('Write probe failed')
            result = metrics(time.monotonic() - outage, age, 1,
                             args.rto_target, args.rpo_target)
            report.update(result, status='passed' if result['objectives_met'] else 'failed',
                          restored_rows=100, data_sha256=digest(actual),
                          backup_sha256=checksum, write_probe=True)
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        drill.cleanup()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('Evidence:', out)
    return 0 if report['status'] == 'passed' else 1


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('Must be a finite positive number')
    return number


def main(argv=None):
    """Run the command line interface and return its process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=['data-loss', 'service-loss', 'corrupt-backup'])
    parser.add_argument('--image', default='postgres:17')
    parser.add_argument('--output', default='artifacts')
    parser.add_argument('--rto-target', type=positive, default=120)
    parser.add_argument('--rpo-target', type=positive, default=60)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())

