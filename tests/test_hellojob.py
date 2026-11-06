import json
import unittest
from bs4 import BeautifulSoup

from parsers.boards import active_hellojob

URL = 'https://www.hellojob.az/vakansiya/junior-helpdesk'


class HelloJobStatus(unittest.TestCase):
    def parse(self, date, badge='', url=URL):
        record = {'@type': 'JobPosting', 'url': url, 'title': 'Junior Helpdesk', 'validThrough': date}
        soup = BeautifulSoup(badge + '<script type="application/ld+json">' + json.dumps(record) + '</script>',
                             'html.parser')
        return active_hellojob(soup, URL, 'Bank')

    def test_explicitly_closed_wins_over_future_deadline(self):
        self.assertIsNone(self.parse('2099-12-31', '<span class="vp__badge--ended">Vaxtı bitib</span>'))

    def test_rejects_expired_unknown_and_unrelated(self):
        for date in ('2000-01-01', '', 'unknown'):
            self.assertIsNone(self.parse(date))
        self.assertIsNone(self.parse('2099-12-31', url=URL+'-other'))

    def test_date_only_includes_last_day_in_baku(self):
        self.assertEqual(self.parse('2099-12-31').valid_until, '2099-12-31T23:59:59.999999+04:00')
