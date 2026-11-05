"""Standard-library bootstrap for the project-local Python environment."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import venv
from contextlib import closing

ROOT = Path(__file__).resolve().parent


def prepare():
    env = ROOT / '.venv'
    env.mkdir(exist_ok=True)
    python = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    # Serialize setup across simultaneous launches. A process exit releases the lock.
    with closing(sqlite3.connect(env / '.setup.sqlite3', timeout=600)) as lock:
        lock.execute('BEGIN EXCLUSIVE')
        if not python.is_file() or not (env / 'pyvenv.cfg').is_file():
            print('Creating the JobRadar environment...', flush=True)
            venv.EnvBuilder(with_pip=True).create(env)
        elif subprocess.run([str(python), '-m', 'pip', '--version'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            subprocess.run([str(python), '-m', 'ensurepip', '--upgrade'], check=True)
        print('Checking JobRadar dependencies...', flush=True)
        # pip reuses installed versions satisfying the requirements, including offline.
        subprocess.run([str(python), '-m', 'pip', '--disable-pip-version-check',
                        '--no-input', 'install', '-q', '-r', str(ROOT / 'requirements.txt')], check=True)
    return python


def main():
    if sys.version_info < (3, 11):
        print('JobRadar requires Python 3.11 or newer.', file=sys.stderr)
        return 1
    try:
        python = prepare()
    except (OSError, subprocess.CalledProcessError, sqlite3.Error) as exc:
        print(f'JobRadar setup failed: {exc}\nCheck your internet connection and that the project folder is writable. '
              'On Ubuntu/Debian, install the venv package for your Python version, then run the same command again.',
              file=sys.stderr)
        return 1
    try:
        return subprocess.call([str(python), '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                                *sys.argv[1:]], cwd=ROOT)
    except KeyboardInterrupt:
        return 0
