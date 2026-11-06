import json
import re
from urllib.parse import quote, urljoin, urlsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from matching.jobs import Job, expired, folded
from scraper.http import FetchError


def plain(html):
    return BeautifulSoup(str(html or ''), 'html.parser').get_text(' ', strip=True)


def pages(get_page, parse):
    offset = 0
    seen = set()
    for page in range(1, 101):
        rows, total = get_page(page, offset)
        if not isinstance(rows, list):
            raise FetchError('Unexpected vacancy list format.')
        keys = {str(r.get('id') or r.get('url') or r.get('slug')) for r in rows}
        batch = [parse(r) for r in rows if not expired(r.get('endDate') or r.get('end_date') or r.get('deadline'))]
        if rows and not keys - seen:
            raise FetchError('Publisher repeated a page. Results may be incomplete.')
        seen.update(keys)
        yield from batch
        offset += len(rows)
        if offset >= total:
            return
        if not rows:
            raise FetchError('Publisher ended pagination before its reported total.')
    raise FetchError('100-page limit reached.')


def bir(client, name, base):
    def page(_, offset):
        data = client.json('https://apihr.kapitalbank.az/api/Vacancy/vacancies'
                           f'?Skip={offset}&Take=50&SortField=id&OrderBy=true')
        rows = data['data']
        # This endpoint can report only the returned slice in totalCount.
        return rows, offset + len(rows) + int(len(rows) == 50)

    def parse(r):
        return Job(r['header'], (r.get('companyDto') or {}).get('displayName') or name,
                   urljoin(base, f"/vacancies/{r['id']}"), plain(r.get('description')),
                   r.get('location') or '', r.get('employmentType') or '')
    return pages(page, parse)


def abb(client, name, endpoint):
    def page(i, _):
        data = client.json(endpoint + f'?page={i}')
        return data['data'], data['total']

    def parse(r):
        return Job(r['title'], name, r['url'], plain(r.get('description')),
                   employment=r.get('type') or '', published=r.get('begin_date') or '')
    return pages(page, parse)


def board_reference(company_slug, title, location, timestamp):
    # Connect portal slugs to employer feed IDs only with a precise publication instant.
    if location and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z', timestamp or ''):
        return 'glorri-post:' + json.dumps([folded(x) for x in (company_slug, title, location, timestamp)])
    return ''


def employer(client, name, company_id):
    api = 'https://api.glorri.com/integration-service/'
    rows = client.json(api + 'jobs/company-page?companyId=' + company_id)
    if not isinstance(rows, list):
        raise FetchError('Unexpected employer feed format.')
    if not rows:
        return
    slug = client.json(api + f'companies/{company_id}/slug')
    for r in rows:
        if expired(r.get('deadline')):
            continue
        url = f"https://glorri.com/{quote(slug, safe='')}/{r['id']}"
        location, published = r.get('location') or '', r.get('postedDate') or ''
        yield Job(r['title'], name, url, plain(r.get('description')), location,
                  r.get('type') or '', published, board_reference(slug, r['title'], location, published))


def portal(client):
    def page(_, offset):
        data = client.json(f'https://jobs.glorri.az/api/jobs/public?limit=18&offset={offset}')
        return data['entities'], data['totalCount']

    def parse(r):
        company = r['company']
        location, published = r.get('location') or '', r.get('postedDate') or ''
        url = r.get('redirectUrl') or f"https://jobs.glorri.az/vacancies/{company['slug']}/{r['slug']}/apply"
        return Job(r['title'], company['name'], url, plain(r.get('description')), location,
                   r.get('type') or '', published, board_reference(company['slug'], r['title'], location, published))
    return pages(page, parse)


def rss(client, url, name):
    xml = ET.fromstring(client.read(url)[0])
    channel = xml.find('channel')
    if channel is None:
        raise FetchError('Unexpected RSS format.')
    for item in channel.findall('item'):
        location = ', '.join(filter(None, [item.findtext('.//{*}city'), item.findtext('.//{*}country')]))
        yield Job(item.findtext('title'), name, item.findtext('link') or '',
                  plain(item.findtext('description')), location, item.findtext('.//{*}employmentType') or '',
                  item.findtext('pubDate') or '')
