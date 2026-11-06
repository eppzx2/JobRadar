import json
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from collections import Counter
from datetime import datetime, timezone

from filelock import FileLock, Timeout

from database.store import as_job, prune, save, setting
from matching.jobs import matches
from matching.profile import eligible, role_hits
from notifications.telegram import notify
from scraper.engine import collect, enrich
from scraper.http import Client, FetchError, PublisherLimits

SOURCE_SECONDS = 50


def fetch(db, progress=lambda text: None, collector=collect, remember=None):
    path = db.execute('PRAGMA database_list').fetchone()[2]
    try:
        with FileLock(path + '.fetch.lock', timeout=0):
            return _fetch(db, progress, collector, remember)
    except Timeout:
        raise FetchError('A fetch is already running. Check back when it finishes.') from None


def read_source(client, source, collector, descriptions, resolved, report):
    aliases = resolved.copy()
    detail_cache = {}
    jobs, warnings = [], Counter()
    detail_failures = 0
    try:
        for job in collector(client, source):
            client.remaining()
            if not job.title or not job.keys():
                warnings['Missing title or identifier'] += 1
                continue
            provider = next((k for k in job.keys() if k.startswith('glorri:')), '')
            if provider in aliases:
                job.aliases.append(aliases[provider])
            if descriptions and not job.description:
                job.description = next((detail_cache[k] for k in job.keys() if k in detail_cache), '')
            needs_slug = provider and provider not in aliases and not job.reference
            needs_detail = needs_slug or (descriptions and eligible(job) and not job.description)
            if needs_detail and detail_failures >= 3:
                warnings['Detail lookups paused after three consecutive failures'] += 1
            elif needs_detail:
                try:
                    enrich(client, job)
                    detail_failures = 0
                    if provider and job.aliases:
                        aliases[provider] = job.aliases[-1]
                except Exception as exc:
                    detail_failures += 1
                    warnings['Detail unavailable: ' + str(exc)[:150]] += 1
            if eligible(job) and job.description:
                for key in job.keys():
                    detail_cache[key] = job.description
            jobs.append(job)
            if len(jobs) % 50 == 0:
                report(f"{source['name']} · {len(jobs)} vacancies read")
    except Exception as exc:
        warnings[str(exc)[:220] or type(exc).__name__] += 1
    return source, jobs, warnings


def _fetch(db, progress, collector, remember):
    sources = list(db.execute('SELECT * FROM sources WHERE enabled ORDER BY id'))
    if not sources:
        raise FetchError('Enable at least one source before fetching.')
    words = [r[0] for r in db.execute('SELECT word FROM keywords ORDER BY id')]
    descriptions = setting(db, 'descriptions')
    telegram = setting(db, 'telegram')
    # The short Unibank application URLs have no portal slug. Resolve them once.
    resolved = dict(db.execute(
        "SELECT a.key,b.key FROM identities a JOIN identities b ON a.job=b.job "
        "WHERE a.key LIKE 'glorri:%' AND b.key LIKE 'glorri-slug:%'"
    ))
    # Keep SQLite and Streamlit calls on the caller thread.
    budget = None if setting(db, 'full_scan') else SOURCE_SECONDS
    events = Queue()
    limits = PublisherLimits()

    def worker(source):
        start = time.monotonic()
        client = Client(limits, start + budget if budget is not None else None)
        events.put(('progress', f"Checking {source['name']}…"))
        try:
            batch = read_source(client, source, collector, descriptions, resolved,
                                lambda message: events.put(('progress', message)))
        finally:
            client.session.close()
        return batch, round(time.monotonic() - start)

    batches = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {s['id']: pool.submit(worker, s) for s in sources}
        for source_id, future in pending.items():
            future.add_done_callback(lambda _, sid=source_id: events.put(('finished', sid)))
        while pending:
            event, value = events.get()
            if event == 'progress':
                progress(value)
                continue
            batch, elapsed = pending.pop(value).result()
            source, jobs, warnings = batch
            batches.append(batch)
            state = 'partial' if warnings and jobs else 'failed' if warnings else 'checked'
            progress(f"{source['name']} · {state} · {len(jobs)} vacancies · {elapsed}s")
    batches.sort(key=lambda batch: batch[0]['id'])
    new_matches = []
    with db:
        run = db.execute('INSERT INTO runs DEFAULT VALUES').lastrowid
        for source, jobs, warnings in batches:
            ids = set()
            for job in jobs:
                jid = save(db, job, run)
                ids.add(jid)
                if eligible(job) and job.description:
                    hits = role_hits(job.description, words, in_description=True)
                    db.execute('UPDATE jobs SET description_hits=? WHERE id=?', (json.dumps(hits), jid))
                    if remember and matches(job, words, descriptions):
                        remember((jid, job.url), job.description)
            status = ('Partial' if ids else 'Failed') if warnings else 'Checked'
            message = ' · '.join(f'{k} ({n})' for k, n in warnings.items())
            db.execute('INSERT INTO checks VALUES (?,?,?,?,?,?)',
                       (run, source['name'], source['url'], status, len(ids), message))
        seen = matched = 0
        for row in db.execute('SELECT * FROM jobs WHERE last_run=?', (run,)):
            seen += 1
            job = as_job(row)
            hits = matches(job, words, descriptions)
            if descriptions and eligible(job):
                saved = json.loads(row['description_hits'])
                hits = [word for word in words if word in hits or word in saved]
            if hits:
                matched += 1
                if row['first_run'] == run:
                    new_matches.append((job, hits))
        db.execute('UPDATE runs SET finished=?,checked=?,discovered=?,matched=?,fresh=? WHERE id=?',
                   (datetime.now(timezone.utc).isoformat(timespec='seconds'), len(sources), seen, matched, len(new_matches), run))
        prune(db)
    free = db.execute('PRAGMA freelist_count').fetchone()[0]
    if free > 512 and free * 3 > db.execute('PRAGMA page_count').fetchone()[0]:
        db.execute('VACUUM')
    if telegram and new_matches:
        progress('Sending new matches to Telegram…')
        message = notify(new_matches)
        with db:
            db.execute('UPDATE runs SET notification=? WHERE id=?', (message, run))
    return run
