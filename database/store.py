import json
import os
import sqlite3
from pathlib import Path

from matching.jobs import Job, folded
from matching.profile import ROLES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORDS = ROLES
FIELDS = ('title', 'company', 'url', 'description', 'location', 'employment', 'published')


def connect(path=None):
    path = Path(path or os.getenv('JOBRADAR_DB', 'data/jobradar.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript((ROOT / 'database/schema.sql').read_text())
    with db:
        seeded = db.execute("INSERT OR IGNORE INTO settings VALUES ('initialized','1')").rowcount
        if seeded:
            sources = json.loads((ROOT / 'config/sources.json').read_text(encoding='utf-8'))
            db.executemany('INSERT INTO sources(name,url) VALUES (?,?)', sources.items())
            db.executemany('INSERT INTO keywords(word,folded) VALUES (?,?)', [(w, folded(w)) for w in DEFAULT_WORDS])
        added_boards = db.execute("INSERT OR IGNORE INTO settings VALUES ('boards_jobsearch_hellojob','1')").rowcount
        if added_boards and not seeded:
            defaults = json.loads((ROOT / 'config/sources.json').read_text(encoding='utf-8'))
            db.executemany('INSERT OR IGNORE INTO sources(name,url) VALUES (?,?)',
                           [(name, defaults[name]) for name in ('JobSearch.az', 'HelloJob.az')])
        cyberjob = db.execute("INSERT OR IGNORE INTO settings VALUES ('board_cyberjob','1')").rowcount
        if cyberjob and not seeded:
            defaults = json.loads((ROOT / 'config/sources.json').read_text(encoding='utf-8'))
            db.execute('INSERT OR IGNORE INTO sources(name,url) VALUES (?,?)', ('CyberJob.az', defaults['CyberJob.az']))
        if db.execute("INSERT OR IGNORE INTO settings VALUES ('hellojob_deadlines_v1','1')").rowcount:
            db.execute("ALTER TABLE jobs ADD COLUMN valid_until TEXT NOT NULL DEFAULT ''")
        upgrade = db.execute("INSERT OR IGNORE INTO settings VALUES ('compact_role_profile_v1','1')").rowcount
        if upgrade:
            db.execute("ALTER TABLE jobs ADD COLUMN description_hits TEXT NOT NULL DEFAULT '[]'")
            if not seeded:
                db.execute("DELETE FROM keywords WHERE folded IN ('internship','trainee','junior')")
                db.executemany('INSERT OR IGNORE INTO keywords(word,folded) VALUES (?,?)',
                               [(w, folded(w)) for w in ROLES])
            db.execute("UPDATE jobs SET description='' WHERE description!=''")
            prune(db)
    if upgrade and not seeded:
        db.execute('VACUUM')
    return db


def prune(db):
    # Compact metadata is useful for returning matches and Telegram deduplication.
    db.execute("""DELETE FROM identities WHERE job IN (
        SELECT j.id FROM jobs j JOIN runs r ON r.id=j.last_run WHERE julianday(r.finished)<julianday('now','-30 days')
        UNION SELECT id FROM (SELECT id FROM jobs ORDER BY last_run DESC,id DESC LIMIT -1 OFFSET 10000))""")
    db.execute('DELETE FROM jobs WHERE id NOT IN (SELECT job FROM identities)')
    db.execute('DELETE FROM checks WHERE run NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 30)')
    db.execute("""DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 30)
        AND id NOT IN (SELECT first_run FROM jobs UNION SELECT last_run FROM jobs)""")


def setting(db, key):
    row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return bool(row and row[0] == '1')


def set_option(db, key, value):
    with db:
        db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, str(int(value))))


def as_job(row):
    return Job(**{k: row[k] for k in FIELDS})


def save(db, job, run):
    keys = job.keys()
    if not keys or not job.title.strip():
        raise ValueError('Vacancy lacks a title or stable identity.')
    existing = list(db.execute('SELECT DISTINCT j.* FROM jobs j JOIN identities i ON i.job=j.id '
                               f'WHERE i.key IN ({",".join("?" for _ in keys)}) ORDER BY j.first_run,j.id', keys))
    values = ['' if k == 'description' else getattr(job, k) or '' for k in FIELDS]
    if existing:
        keep = existing[0]['id']
        for row in existing:
            values = [v or row[k] for v, k in zip(values, FIELDS)]
            if row['id'] != keep:
                db.execute('UPDATE identities SET job=? WHERE job=?', (keep, row['id']))
                db.execute('DELETE FROM jobs WHERE id=?', (row['id'],))
        db.execute('UPDATE jobs SET last_run=?,' + ','.join(k+'=?' for k in FIELDS) + ' WHERE id=?',
                   (run, *values, keep))
    else:
        keep = db.execute('INSERT INTO jobs(first_run,last_run,' + ','.join(FIELDS) +
                          ') VALUES (?,?,?,?,?,?,?,?,?)', (run, run, *values)).lastrowid
    if job.valid_until:
        db.execute('UPDATE jobs SET valid_until=? WHERE id=?', (job.valid_until, keep))
    db.executemany('INSERT OR IGNORE INTO identities VALUES (?,?)', [(k, keep) for k in keys])
    return keep
