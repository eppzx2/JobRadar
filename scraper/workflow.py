from collections import Counter
from datetime import datetime, timezone

from filelock import FileLock, Timeout

from database.store import as_job, save, setting
from matching.jobs import matches
from notifications.telegram import notify
from scraper.engine import collect, enrich
from scraper.http import Client, FetchError


def fetch(db, progress=lambda text: None, collector=collect):
    path = db.execute('PRAGMA database_list').fetchone()[2]
    try:
        with FileLock(path + '.fetch.lock', timeout=0):
            return _fetch(db, progress, collector)
    except Timeout:
        raise FetchError('A fetch is already running. Check back when it finishes.') from None


def _fetch(db, progress, collector):
    sources = list(db.execute('SELECT * FROM sources WHERE enabled ORDER BY id'))
    if not sources:
        raise FetchError('Enable at least one source before fetching.')
    words = [r[0] for r in db.execute('SELECT word FROM keywords ORDER BY id')]
    descriptions = setting(db, 'descriptions')
    telegram = setting(db, 'telegram')
    client = Client()
    # Network I/O precedes the write transaction; keep partial pages on source failure.
    batches = []
    detail_cache = {}
    # The short Unibank application URLs have no portal slug. Resolve them once.
    resolved = dict(db.execute(
        "SELECT a.key,b.key FROM identities a JOIN identities b ON a.job=b.job "
        "WHERE a.key LIKE 'glorri:%' AND b.key LIKE 'glorri-slug:%'"
    ))
    if descriptions:
        for row in db.execute("SELECT i.key,j.description FROM identities i JOIN jobs j ON i.job=j.id WHERE j.description!=''"):
            detail_cache[row[0]] = row[1]
    try:
        for source in sources:
            progress(f"Checking {source['name']}…")
            jobs, warnings = [], Counter()
            detail_failures = 0
            try:
                for job in collector(client, source):
                    if not job.title or not job.keys():
                        warnings['Missing title or identifier'] += 1
                        continue
                    provider = next((k for k in job.keys() if k.startswith('glorri:')), '')
                    if provider in resolved:
                        job.aliases.append(resolved[provider])
                    if descriptions and not job.description:
                        job.description = next((detail_cache[k] for k in job.keys() if k in detail_cache), '')
                    needs_slug = provider and provider not in resolved and not job.reference
                    needs_detail = needs_slug or (descriptions and not job.description)
                    if needs_detail and detail_failures >= 3:
                        warnings['Detail lookups paused after three consecutive failures'] += 1
                    elif needs_detail:
                        try:
                            enrich(client, job)
                            detail_failures = 0
                            if provider and job.aliases:
                                resolved[provider] = job.aliases[-1]
                        except Exception as exc:
                            detail_failures += 1
                            warnings['Detail unavailable: ' + str(exc)[:150]] += 1
                    if job.description:
                        for key in job.keys():
                            detail_cache[key] = job.description
                    jobs.append(job)
                    if len(jobs) % 50 == 0:
                        progress(f"{source['name']} · {len(jobs)} vacancies read")
            except Exception as exc:
                warnings[str(exc)[:220] or type(exc).__name__] += 1
            batches.append((source, jobs, warnings))
    finally:
        client.session.close()
    new_matches = []
    with db:
        run = db.execute('INSERT INTO runs DEFAULT VALUES').lastrowid
        for source, jobs, warnings in batches:
            ids = {save(db, j, run) for j in jobs}
            status = ('Partial' if ids else 'Failed') if warnings else 'Checked'
            message = ' · '.join(f'{k} ({n})' for k, n in warnings.items())
            db.execute('INSERT INTO checks VALUES (?,?,?,?,?,?)',
                       (run, source['name'], source['url'], status, len(ids), message))
        seen = matched = 0
        for row in db.execute('SELECT * FROM jobs WHERE last_run=?', (run,)):
            seen += 1
            job = as_job(row)
            hits = matches(job, words, descriptions)
            if hits:
                matched += 1
                if row['first_run'] == run:
                    new_matches.append((job, hits))
        db.execute('UPDATE runs SET finished=?,checked=?,discovered=?,matched=?,fresh=? WHERE id=?',
                   (datetime.now(timezone.utc).isoformat(timespec='seconds'), len(sources), seen, matched, len(new_matches), run))
    if telegram and new_matches:
        progress('Sending new matches to Telegram…')
        message = notify(new_matches)
        with db:
            db.execute('UPDATE runs SET notification=? WHERE id=?', (message, run))
    return run
