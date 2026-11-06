import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from scraper.engine import collect


class GlorriScope(unittest.TestCase):
    def test_scope_on_every_page(self):
        for full in (False, True):
            with self.subTest(full=full):
                client = Mock()
                client.json.side_effect = [
                    {'totalCount': 2, 'entities': [{'slug': str(i), 'title': 'Junior SOC Analyst',
                                                    'company': {'name': 'Test', 'slug': 'test'}}]}
                    for i in range(2)
                ]
                source = {'name': 'Glorri', 'url': 'https://jobs.glorri.az/', 'full_scan': full}
                self.assertEqual(len(list(collect(client, source))), 2)
                client.read.assert_not_called()
                for i, call in enumerate(client.json.call_args_list):
                    query = parse_qs(urlsplit(call.args[0]).query)
                    self.assertEqual(query['offset'], [str(i)])
                    self.assertEqual(query.get('jobFunctions[]'), None if full else ['science-technology-engineering'])
