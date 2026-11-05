"""Optional selectors for conventional HTML boards that do not publish JobPosting data."""
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from matching.jobs import Job
from scraper.http import FetchError


def configured_board(client, soup, base, name, rules):
    seen = set()
    for _ in range(80):
        if base in seen:
            raise FetchError('Pagination loop in configured board.')
        seen.add(base)
        cards = soup.select(rules['card'])
        if not cards:
            if rules.get('empty') and soup.select_one(rules['empty']):
                return
            raise FetchError('Configured card selector found no vacancies.')
        for card in cards:
            title = card.select_one(rules['title'])
            link = card.select_one(rules['link'])
            if not title or not link or not link.get('href'):
                raise FetchError('A configured card lacks a title or application link.')
            fields = {}
            for key in ('description', 'location', 'employment', 'published'):
                if rules.get(key) and (el := card.select_one(rules[key])):
                    fields[key] = el.get_text(' ', strip=True)
            yield Job(title.get_text(' ', strip=True), name, urljoin(base, link['href']), **fields)
        next_link = soup.select_one(rules['next']) if rules.get('next') else None
        if not next_link or not next_link.get('href'):
            return
        target = urljoin(base, next_link['href'])
        if urlsplit(target).netloc != urlsplit(base).netloc:
            raise FetchError('Pagination left the configured host.')
        html, base = client.read(target)
        soup = BeautifulSoup(html, 'html.parser')
    raise FetchError('Configured board reached its page limit.')
