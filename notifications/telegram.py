import os
import time

import requests


def configured():
    return bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'))


def notify(jobs):
    if not configured():
        return 'Telegram credentials missing. No messages sent.'
    sent = 0
    for job, words in jobs:
        if sent:
            time.sleep(1.1)
        message = f'{job.title} · {job.company}\n{job.location}\nMatched: {", ".join(words)}\n{job.url}'
        try:
            r = requests.post('https://api.telegram.org/bot' + os.environ['TELEGRAM_BOT_TOKEN'] + '/sendMessage',
                              json={'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': message[:4096]},
                              timeout=(4, 10), allow_redirects=False)
            if r.status_code != 200 or not r.json().get('ok'):
                break
        except (requests.RequestException, ValueError):
            break  # Never surface exceptions containing credential-bearing URLs.
        sent += 1
    return f'Telegram delivered {sent} of {len(jobs)} new matches.'
