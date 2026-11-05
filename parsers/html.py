import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from matching.jobs import Job, expired
from parsers.feeds import plain
from scraper.http import FetchError


def postings(node):
    if isinstance(node, list):
        for value in node:
            yield from postings(value)
    elif isinstance(node, dict):
        types = node.get('@type', [])
        if 'JobPosting' in (types if isinstance(types, list) else [types]):
            yield node
        else:
            for value in node.values():
                yield from postings(value)


def structured(soup, url, name):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        for r in postings(data):
            if not r.get('title') or expired(r.get('validThrough')):
                continue
            org = r.get('hiringOrganization') or {}
            company = org.get('name', name) if isinstance(org, dict) else name
            places = r.get('jobLocation') or []
            locations = []
            for place in places if isinstance(places, list) else [places]:
                address = place.get('address') if isinstance(place, dict) else place
                if isinstance(address, dict):
                    address = address.get('addressLocality') or address.get('addressRegion')
                if address:
                    locations.append(str(address))
            link = urljoin(url, r['url']) if r.get('url') else ''
            ident = r.get('identifier') or {}
            reference = ident.get('value') if isinstance(ident, dict) else ident
            reference = f'requisition:{company.casefold()}:{reference}' if reference else ''
            typ = r.get('employmentType') or ''
            yield Job(r['title'], company, link, plain(r.get('description')), ', '.join(locations),
                      ', '.join(typ) if isinstance(typ, list) else typ, r.get('datePosted') or '', reference)


def generic(client, soup, base, name, detail=False):
    jobs = list(structured(soup, base, name))
    if jobs:
        for job in jobs:
            if not job.url and len(jobs) == 1 and (detail or re.search(
                    r'/(?:jobs|job|vacancies|vakansiyalar)/[^/]+/?$', urlsplit(base).path)):
                job.url = base
            yield job
        return
    links = set()
    for a in soup.select('main a[href], article a[href], a[itemprop="url"]'):
        link = urljoin(base, a['href'].strip())
        path = urlsplit(link).path.strip('/').split('/')
        if (link != base and urlsplit(link).hostname == urlsplit(base).hostname and
                any(part in ('jobs', 'vacancies', 'vakansiyalar', 'job') for part in path[:-1])):
            links.add(link)
    if not links:
        raise FetchError('No recognizable job listings. A source-specific parser may be required.')
    for link in sorted(links)[:80]:
        html, final = client.read(link)
        found = list(structured(BeautifulSoup(html, 'html.parser'), final, name))
        for job in found:
            if not job.url and len(found) == 1:
                job.url = final
            yield job
    if len(links) > 80:
        raise FetchError('80 detail-page limit reached.')


def unibank(soup, base, name):
    cards = soup.select('.vacancy')
    if not cards:
        raise FetchError('Unibank listing markup was not recognized.')
    for card in cards:
        date = card.select_one('.vacancy__date')
        deadline = re.search(r'\d{2}\.\d{2}\.\d{4}', date.get_text()) if date else None
        if deadline and expired(deadline[0]):
            continue
        title = card.select_one('.vacancy__name')
        link = card.select_one('a.button--apply[href]')
        if not title or not link:
            raise FetchError('Unibank vacancy lacks its title or application link.')
        body = card.select_one('.accordion__body, .vacancy__description, .accordion__content')
        yield Job(title.get_text(' ', strip=True), name, urljoin(base, link['href']),
                  body.get_text(' ', strip=True) if body else '')
