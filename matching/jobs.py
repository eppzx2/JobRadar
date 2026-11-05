from datetime import datetime
from zoneinfo import ZoneInfo
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def clean_url(url):
    parts = urlsplit(url.strip())
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Enter a public HTTP or HTTPS URL.')
    return parts.geturl()


def identity_url(url):
    p = urlsplit(clean_url(url))
    host = p.hostname.lower()
    if p.port and (p.scheme, p.port) not in [('https', 443), ('http', 80)]:
        host += f':{p.port}'
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid'}]
    # Hash routers sometimes put the actual vacancy ID in the fragment.
    fragment = p.fragment if p.fragment.startswith(('/', '!')) else ''
    return urlunsplit((p.scheme, host, p.path.rstrip('/') or '/', urlencode(sorted(query)), fragment))


def folded(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().replace('i\u0307', 'i').split())


def expired(value):
    """Use the publisher's local deadline day when only a calendar date is supplied."""
    if not value:
        return False
    now = datetime.now(ZoneInfo('Asia/Baku'))
    try:
        if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', value):
            return datetime.strptime(value, '%d.%m.%Y').date() < now.date()
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date < now if date.tzinfo else date.date() < now.date()
    except (ValueError, TypeError):
        return False


@dataclass
class Job:
    title: str
    company: str
    url: str = ''
    description: str = ''
    location: str = ''
    employment: str = ''
    published: str = ''
    reference: str = ''  # Provider-scoped authoritative ID, never a title fingerprint.

    aliases: list[str] = field(default_factory=list)

    def __post_init__(self):
        for name in ('title', 'company', 'url', 'description', 'location', 'employment', 'published', 'reference'):
            value = getattr(self, name)
            if value is None:
                setattr(self, name, '')
            elif not isinstance(value, str):
                raise ValueError(f'Unexpected vacancy field format: {name}')

    def keys(self):
        keys = []
        if self.url:
            keys.append(identity_url(self.url))
            p = urlsplit(self.url)
            if p.hostname in ('glorri.com', 'jobs.glorri.com', 'glorri.az', 'jobs.glorri.az'):
                if p.hostname == 'jobs.glorri.az' and p.path.startswith('/vacancies/'):
                    keys.append('glorri-slug:' + p.path.rstrip('/').removesuffix('/apply'))
                m = re.search(r'/([0-9a-f]{24})(?=[-/]|$)', p.path, re.I)
                if m:
                    keys.append('glorri:' + m[1].lower())
        if self.reference:
            keys.append(self.reference)
        return list(dict.fromkeys(keys + self.aliases))


def matches(job, keywords, descriptions):
    fields = [folded(job.title)]
    if descriptions:
        fields.append(folded(job.description))
    return [word for word in keywords if any(folded(word) in field for field in fields)]
