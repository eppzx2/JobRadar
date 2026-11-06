import json
import unittest
from unittest.mock import Mock

from parsers.boards import JOBSEARCH_API, JOBSEARCH_CATEGORIES
from scraper.engine import collect
from scraper.http import FetchError


class JobSearchScope(unittest.TestCase):
    def run_board(self, full, next_url=None):
        client = Mock()
        row = {'id': 1, 'slug': 'junior-helpdesk', 'title': 'Junior Helpdesk'}
        client.read.side_effect = [(json.dumps({'items': [row], 'next': next_url}), JOBSEARCH_API),
                                   (json.dumps({'items': [], 'next': None}), next_url)]
        jobs = list(collect(client, {'name': 'JobSearch.az', 'url': 'https://jobsearch.az/vacancies',
                                     'full_scan': full}))
        return jobs, [call.args[0] for call in client.read.call_args_list]

    def test_quick_requests_filtered_api_and_follows_filtered_cursor(self):
        target = JOBSEARCH_API + '?page=2&categories=' + JOBSEARCH_CATEGORIES
        jobs, requests = self.run_board(False, target)
        self.assertEqual(len(jobs), 1)
        self.assertIn('categories=' + JOBSEARCH_CATEGORIES, requests[0])
        self.assertEqual(requests[1:], [target])

    def test_full_uses_all_categories(self):
        _, requests = self.run_board(True)
        self.assertNotIn('categories=', requests[0])

    def test_quick_does_not_follow_unfiltered_cursor(self):
        with self.assertRaises(FetchError):
            self.run_board(False, JOBSEARCH_API + '?page=2')
