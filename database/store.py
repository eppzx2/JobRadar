import json
import os
import sqlite3
from pathlib import Path

from matching.jobs import Job, folded

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORDS = ['SOC Analyst', 'Cybersecurity', 'Information Security', 'Blue Team',
                 'Security Analyst', 'IT Support', 'System Administrator', 'Network Engineer',
                 'Junior', 'Internship', 'Trainee']
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
    return db


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
    values = [getattr(job, k) or '' for k in FIELDS]
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
    db.executemany('INSERT OR IGNORE INTO identities VALUES (?,?)', [(k, keep) for k in keys])
    return keep
