import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from parsers import boards, feeds
from parsers.selectors import configured_board
from parsers.html import generic, unibank
from scraper.http import FetchError


def collect(client, source):
    name, url = source['name'], source['url']
    config = Path(__file__).resolve().parents[1] / 'config/selectors.json'
    rules = json.loads(config.read_text(encoding='utf-8')).get(url)
    targeted = not dict(source).get('full_scan', False)
    if not rules and url.rstrip('/') == 'https://jobs.glorri.az':
        yield from feeds.portal(client, targeted=targeted)
        return
    if not rules and url.rstrip('/') == 'https://jobsearch.az/vacancies':
        yield from boards.jobsearch(client, targeted=targeted)
        return
    html, base = client.read(url)
    soup = BeautifulSoup(html, 'html.parser')
    host = urlsplit(base).hostname
    path = urlsplit(base).path.rstrip('/')
    if rules:
        yield from configured_board(client, soup, base, name, rules)
    elif host == 'cyberjob.az' and path == '/vacancies':
        yield from boards.cyberjob(client, soup, base)
    elif host == 'jobsearch.az' and path == '/vacancies':
        yield from boards.jobsearch(client, targeted=targeted)
    elif host in ('hellojob.az', 'www.hellojob.az') and path == '/vakansiyalar':
        yield from boards.hellojob(client, soup, base)
    elif host == 'careers.bir.az' and path == '/vacancies':
        yield from feeds.bir(client, name, base)
    elif soup.select_one('form.js-vacancy-filter[action]'):
        endpoint = soup.select_one('form.js-vacancy-filter')['action'].strip()
        yield from feeds.abb(client, name, urljoin(base, endpoint))
    elif host == 'jobs.glorri.az' and not path:
        yield from feeds.portal(client, targeted=targeted)
    elif host == 'unibank.az' and 'vacanciesHrm' in path:
        yield from unibank(soup, base, name)
    elif host == 'www.rabitabank.com' and soup.find('vacancies'):
        branches = json.loads(soup.find('vacancies')[':branches'])
        yield from feeds.employer(client, name, branches[0]['companyId'])
    elif host == 'www.pashabank.az' and path.endswith('/vakansiyalar'):
        # Public tenant used by the bank's career frontend.
        yield from feeds.employer(client, name, '5fb515572dc2eb08ab144923')
    elif embed := re.search(r"gmb_embed\(\s*['\"]([0-9a-f]{24})['\"]", html):
        yield from feeds.employer(client, name, embed[1])
    elif rss := soup.select_one('link[type="application/rss+xml"][href*="jobs"]'):
        yield from feeds.rss(client, urljoin(base, rss['href']), name)
    else:
        count = 0
        for job in generic(client, soup, base, name):
            count += 1
            yield job
        if not count:
            raise FetchError('Linked pages lacked recognizable vacancy data.')


def enrich(client, job):
    """Glorri's lightweight lists omit full descriptions; fetch only in description mode."""
    if not job.description and urlsplit(job.url).hostname == 'cyberjob.az':
        job.description = boards.cyberjob_description(client, job.url)
        return
    if not job.description and urlsplit(job.url).hostname in ('jobsearch.az', 'hellojob.az', 'www.hellojob.az'):
        boards.enrich_board(client, job)
        return
    if job.description or urlsplit(job.url).hostname not in ('glorri.com', 'jobs.glorri.az'):
        return
    url = job.url.removesuffix('/apply')
    html, final = client.read(url)
    soup = BeautifulSoup(html, 'html.parser')
    job.description = ' '.join(x.get_text(' ', strip=True) for x in soup.select('.description-html'))
    if not job.description:
        meta = soup.select_one('meta[property="og:description"]')
        job.description = meta.get('content', '') if meta else ''
    canonical = soup.select_one('meta[property="og:url"]')
    if canonical:
        p = urlsplit(canonical.get('content', ''))
        if p.hostname == 'jobs.glorri.az' and p.path.startswith('/vacancies/'):
            job.aliases.append('glorri-slug:' + p.path.rstrip('/'))


def live_description(client, job):
    """Fetch details only when the reader opens an individual vacancy."""
    host = urlsplit(job.url).hostname
    if host in ('cyberjob.az', 'glorri.com', 'jobs.glorri.az', 'jobsearch.az', 'hellojob.az', 'www.hellojob.az'):
        enrich(client, job)
        return job.description
    html, base = client.read(job.url)
    soup = BeautifulSoup(html, 'html.parser')
    from parsers.html import structured
    for detail in structured(soup, base, job.company):
        if detail.description and (detail.title == job.title or detail.url == job.url):
            return detail.description
    body = soup.select_one('[itemprop="description"], .body-text, .job-description, .vacancy-description, article')
    return body.get_text('\n', strip=True) if body else ''
