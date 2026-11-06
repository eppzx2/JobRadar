import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from filelock import FileLock

from database.store import connect, save, set_option
from matching.jobs import Job, identity_url, matches
from notifications.telegram import notify
from parsers.feeds import abb, bir, employer, portal, rss
from parsers.html import structured, unibank
from parsers.selectors import configured_board
from scraper.http import Client, FetchError
from scraper.workflow import fetch

FIXTURE = Path(__file__).parent / 'fixtures/sample_board.html'


def samples():
    return list(structured(BeautifulSoup(FIXTURE.read_text(), 'html.parser'), 'https://example.test/', 'Board'))


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'jobs.db'
        self.db = connect(self.path)
        with self.db:
            self.db.execute('UPDATE sources SET enabled=(id<=2)')

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def collector(self, client, source):
        if source['id'] == 1:
            yield from samples()
        else:
            yield Job('Junior SOC Analyst', 'Fixture Lab', 'https://example.test/apply?id=17')
            raise FetchError('Publisher timed out')

    def test_history_matching_and_notifications(self):
        set_option(self.db, 'telegram', True)
        with patch('scraper.workflow.notify', return_value='delivered') as send:
            fetch(self.db, collector=self.collector)
            self.assertEqual(len(send.call_args.args[0]), 2)
            self.db.close()
            self.db = connect(self.path)
            set_option(self.db, 'descriptions', True)
            fetch(self.db, collector=self.collector)
            self.assertEqual(send.call_count, 1)
        runs = self.db.execute('SELECT discovered,matched,fresh FROM runs ORDER BY id').fetchall()
        self.assertEqual([tuple(r) for r in runs], [(3, 2, 2), (3, 2, 0)])
        row = self.db.execute('SELECT status FROM checks WHERE run=1 ORDER BY rowid DESC').fetchone()
        self.assertEqual(row[0], 'Partial')

    def test_slow_source_keeps_partial_rows_while_another_completes(self):
        from threading import Barrier

        overlap = Barrier(2, timeout=3)
        def collect(client, source):
            overlap.wait()
            yield Job('Junior Helpdesk', 'Test', f"https://example.test/{source['id']}")
            if source['id'] == 1:
                client.deadline = 0
                client.remaining()

        fetch(self.db, collector=collect)
        checks = self.db.execute('SELECT status,count FROM checks ORDER BY rowid').fetchall()
        self.assertEqual([tuple(row) for row in checks], [('Partial', 1), ('Checked', 1)])

    def test_full_scan_can_finish_more_than_fifty_rows(self):
        set_option(self.db, 'full_scan', True)
        def collect(client, source):
            assert client.deadline is None
            for i in range(60):
                yield Job('Junior Helpdesk', 'Test', f'https://example.test/{i}')
        fetch(self.db, collector=collect)
        self.assertEqual(self.db.execute('SELECT discovered FROM runs').fetchone()[0], 60)

    def test_failure_isolated(self):
        def collect(client, source):
            if source['id'] == 1:
                raise ValueError('Bad HTML')
            return samples()
        fetch(self.db, collector=collect)
        self.assertEqual([r[0] for r in self.db.execute('SELECT status FROM checks')], ['Failed', 'Checked'])

    def test_overlap_lock(self):
        with FileLock(str(self.path) + '.fetch.lock'):
            with self.assertRaisesRegex(FetchError, 'already running'):
                fetch(self.db)

    def test_alias_bridge_preserves_oldest(self):
        with self.db:
            for i in range(2):
                self.db.execute('INSERT INTO runs DEFAULT VALUES')
            a = Job('Engineer', 'Bank', 'https://example.test/a')
            b = Job('Engineer', 'Bank', 'https://example.test/b', reference='ats:234')
            save(self.db, a, 1)
            save(self.db, b, 2)
            a.reference = b.reference
            save(self.db, a, 2)
        self.assertEqual(tuple(self.db.execute('SELECT count(*),min(first_run) FROM jobs').fetchone()), (1, 1))

    def test_deleted_defaults_stay_deleted(self):
        with self.db:
            self.db.execute('DELETE FROM keywords')
            self.db.execute('DELETE FROM sources')
        self.db.close()
        self.db = connect(self.path)
        self.assertFalse(self.db.execute('SELECT * FROM keywords').fetchall())
        with self.assertRaises(FetchError):
            fetch(self.db)


class Parsing(unittest.TestCase):
    def test_case_scope_and_tracking(self):
        j = samples()[0]
        self.assertEqual(matches(j, ['soc ANALYST','blue team'], False), ['soc ANALYST'])
        self.assertEqual(matches(j, ['Blue Team'], True), ['Blue Team'])
        self.assertEqual(identity_url(j.url), 'https://example.test/apply?id=17')
        self.assertNotEqual(identity_url(j.url), identity_url(samples()[1].url))

    def test_abb_pages_and_bir(self):
        client = Mock()
        client.json.side_effect = [{'data':[{'title':'Ops','id':i,'url':f'https://example.test/{i}'}], 'total':2}
                                   for i in (1,2)]
        self.assertEqual(len(list(abb(client, 'ABB', 'https://example.test/api'))), 2)
        client.json.side_effect = None
        client.json.return_value = {'data':[{'id':2,'header':'Support','companyDto':{'displayName':'Bir'}}], 'totalCount':1}
        self.assertEqual(list(bir(client, 'Bir', 'https://careers.bir.az/'))[0].url, 'https://careers.bir.az/vacancies/2')

    def test_cross_board_identity(self):
        row = {'title':'SOC Analyst','id':'f'*24,'location':'Baku','postedDate':'2026-01-01T10:03:23.123Z'}
        client = Mock()
        client.json.side_effect = [[row], 'test-bank', {'totalCount':1, 'entities':[
            dict(row, slug='role-234', company={'slug':'test-bank','name':'Test Bank'})]}]
        a = list(employer(client, 'Test Bank', 'tenant'))[0]
        b = list(portal(client))[0]
        self.assertTrue(set(a.keys()) & set(b.keys()))
        c = Job(a.title, a.company, 'https://example.test/other-id')
        self.assertFalse(set(a.keys()) & set(c.keys()))

    def test_unibank_and_rss(self):
        soup = BeautifulSoup('<div class="vacancy"><p class="vacancy__name">Analyst</p>'
                             '<a class="button--apply" href="/apply/1">Apply</a></div>', 'html.parser')
        self.assertEqual(list(unibank(soup,'https://example.test','Bank'))[0].title,'Analyst')
        client = Mock()
        client.read.return_value = ('<rss><channel><item><title>Internship</title><link>https://example.test/1</link>'
                                    '<description>Office</description></item></channel></rss>', '')
        self.assertEqual(list(rss(client, 'unused', 'Test'))[0].description, 'Office')

    def test_expired_abb_vacancy_excluded(self):
        client = Mock()
        client.json.return_value = {'data': [
            {'id': 17, 'title': 'Expired', 'url': 'https://example.test/17', 'end_date': '01.01.2020'},
            {'id': 18, 'title': 'Open', 'url': 'https://example.test/18', 'end_date': '31.12.2099'}
        ], 'total': 2}
        self.assertEqual([j.title for j in abb(client, 'Test', 'https://example.test/api')], ['Open'])

    def test_selectors_and_next_page(self):
        card = '<article><h2>Network Engineer</h2><a href="/apply/1">Apply</a></article>'
        first = BeautifulSoup(card + '<a rel="next" href="/page/2">Next</a>', 'html.parser')
        client = Mock()
        client.read.return_value = (card.replace('/1', '/2'), 'https://example.test/page/2')
        rules = {'card': 'article', 'title': 'h2', 'link': 'a', 'next': 'a[rel=next]'}
        jobs = list(configured_board(client, first, 'https://example.test', 'Test', rules))
        self.assertEqual([j.url for j in jobs], ['https://example.test/apply/1', 'https://example.test/apply/2'])

    def test_robots_disallows_before_request(self):
        from protego import Protego
        client = Client()
        client.rules['https://example.test'] = Protego.parse('User-agent: *\nDisallow: /private')
        with patch('scraper.http.public_url'), patch.object(client.session, 'get') as get:
            with self.assertRaises(FetchError):
                client.read('https://example.test/private')
            get.assert_not_called()
        client.session.close()

    def test_telegram_failure_hides_credentials(self):
        with patch.dict(os.environ, TELEGRAM_BOT_TOKEN='test-secret', TELEGRAM_CHAT_ID='123'), \
                patch('notifications.telegram.requests.post', return_value=Mock(status_code=429)):
            self.assertEqual(notify([(samples()[0], ['Junior'])]), 'Telegram delivered 0 of 1 new matches.')


if __name__ == '__main__':
    unittest.main()
