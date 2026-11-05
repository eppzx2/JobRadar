import json
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup

from matching.jobs import Job
from parsers.feeds import plain
from parsers.html import structured
from scraper.http import FetchError

JOBSEARCH_API = 'https://jobsearch.az/api-az/vacancies-az'
JSON_HEADERS = {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}


def jobsearch(client):
    url = JOBSEARCH_API + '?hl=az&page=1'
    seen = set()
    for _ in range(100):
        data = json.loads(client.read(url, headers=JSON_HEADERS)[0])
        rows = data['items']
        previous = len(seen)
        for row in rows:
            if row['id'] in seen:
                continue
            seen.add(row['id'])
            company = (row.get('company') or {}).get('title') or 'Undisclosed employer'
            yield Job(row['title'], company, 'https://jobsearch.az/vacancies/' + quote(row['slug'], safe=''),
                      published=row.get('created_at') or '')
        url = data.get('next')
        if not url:
            return
        parsed = urlsplit(url)
        if (len(seen) == previous or parsed.scheme != 'https' or
                parsed.hostname not in ('unsu.jobsearch.az', 'jobsearch.az') or
                parsed.path != '/api-az/vacancies-az'):
            raise FetchError('Unexpected JobSearch pagination.')
    raise FetchError('100-page JobSearch limit reached.')


def hellojob(client, soup, base):
    seen = set()
    for _ in range(100):
        cards = soup.select('a.vacancies__body[href*="/vakansiya/"]')
        if not cards:
            raise FetchError('HelloJob vacancy cards were not found.')
        previous = len(seen)
        for card in cards:
            url = urljoin(base, card['href'])
            if url in seen:
                continue
            seen.add(url)
            title = card.select_one('.vacancies__title')
            company = card.select_one('.vacancies__company-name')
            calendar = card.find('use', attrs={'xlink:href': '#svg-calendar'})
            date = calendar.find_parent('li') if calendar else None
            yield Job(title.get_text(' ', strip=True), company.get_text(' ', strip=True) if company else 'Undisclosed employer',
                      url, published=date.get_text(' ', strip=True) if date else '')
        link = soup.select_one('a.pagination__btn.next[href]')
        if not link:
            return
        target = urljoin(base, link['href'])
        if len(seen) == previous or urlsplit(target).netloc != urlsplit(base).netloc:
            raise FetchError('Unexpected HelloJob pagination.')
        html, base = client.read(target)
        soup = BeautifulSoup(html, 'html.parser')
    raise FetchError('100-page HelloJob limit reached.')


def enrich_board(client, job):
    if urlsplit(job.url).hostname == 'jobsearch.az':
        slug = urlsplit(job.url).path.rsplit('/', 1)[-1]
        row = json.loads(client.read(f'{JOBSEARCH_API}/{slug}?hl=az', headers=JSON_HEADERS)[0])
        job.description = plain(row.get('text'))
    else:
        html, base = client.read(job.url)
        soup = BeautifulSoup(html, 'html.parser')
        detail = next(structured(soup, base, job.company), None)
        if detail:
            job.description = detail.description
            job.employment = detail.employment
            job.location = detail.location
            job.published = detail.published or job.published
    if not job.description:
        raise FetchError('Vacancy description unavailable.')
