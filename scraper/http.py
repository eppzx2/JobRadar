import ipaddress
import json
import os
import socket
import time
from urllib.parse import urljoin, urlsplit

import requests
from protego import Protego

from matching.jobs import clean_url


class FetchError(Exception):
    pass


def public_url(url):
    clean_url(url)
    p = urlsplit(url)
    # An explicitly trusted egress proxy can own DNS and block private destinations.
    proxy = requests.utils.select_proxy(url, requests.utils.get_environ_proxies(url))
    if os.getenv('JOBRADAR_TRUST_EGRESS_PROXY') == '1' and proxy:
        if '.' not in p.hostname or p.hostname.endswith(('.local', '.localhost', '.internal')):
            raise FetchError('Only public internet addresses are permitted.')
        try:
            if not ipaddress.ip_address(p.hostname).is_global:
                raise FetchError('Only public internet addresses are permitted.')
        except ValueError:
            pass
        return url
    addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
    if not all(ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise FetchError('Only public internet addresses are permitted.')
    return url


class Client:
    """One user-triggered run owns this session, policy cache and pacing state."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'JobRadar/1.0', 'Accept-Language': 'az,en;q=0.8'})
        self.rules = {}
        self.last = {}
        self.limited = set()

    def read(self, url, policy=False, hops=0):
        public_url(url)
        p = urlsplit(url)
        origin = f'{p.scheme}://{p.netloc}'
        if origin in self.limited:
            raise FetchError(f'Publisher rate limit at {p.hostname}.')
        delay = 2.0 if p.hostname == 'jobs.glorri.az' else 0.6
        if not policy:
            if origin not in self.rules:
                try:
                    content, _ = self.read(origin + '/robots.txt', policy=True)
                    self.rules[origin] = Protego.parse(content)
                except Exception:
                    self.rules[origin] = None
                    raise
            rules = self.rules[origin]
            if rules is None or not rules.can_fetch(url, 'JobRadar'):
                raise FetchError('Access restricted by robots policy.')
            rate = rules.request_rate('JobRadar')
            delay = max(delay, rules.crawl_delay('JobRadar') or 0, rate.seconds / rate.requests if rate and rate.requests else 0)
            if delay > 30:
                raise FetchError('Publisher requests a longer delay than this interactive fetch supports.')
        time.sleep(max(0, self.last.get(origin, 0) + delay - time.monotonic()))
        self.last[origin] = time.monotonic()
        with self.session.get(url, timeout=(12, 18), allow_redirects=False, stream=True) as response:
            if response.is_redirect:
                if hops >= 4:
                    raise FetchError('Redirect limit reached.')
                return self.read(urljoin(url, response.headers['Location']), policy, hops + 1)
            if policy and response.status_code in (404, 410):
                return '', url
            if response.status_code == 429:
                self.limited.add(origin)
            if response.status_code != 200:
                raise FetchError(f'HTTP {response.status_code} at {p.hostname}' + (' (robots.txt)' if policy else ''))
            buf = bytearray()
            for chunk in response.iter_content(65536):
                buf.extend(chunk)
                if len(buf) > 8_000_000:
                    raise FetchError('Response exceeds the 8 MB limit.')
            encoding = response.encoding
            if not encoding or encoding.lower() == 'iso-8859-1':
                encoding = 'utf-8'
            return buf.decode(encoding, errors='replace'), url

    def json(self, url):
        return json.loads(self.read(url)[0])
