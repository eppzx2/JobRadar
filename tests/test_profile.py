import tempfile
import unittest
from pathlib import Path

from database.store import connect
from matching.jobs import Job, matches
from matching.profile import ROLES
from scraper.workflow import fetch


class Profile(unittest.TestCase):
    def test_bilingual_role_and_level(self):
        for title in ['IT Intern', 'SOC Analyst Intern', 'Junior Help-Desk Technician',
                      'Texniki destek uzre kicik mutexessis', 'Şəbəkə mühəndisi (təcrübəçi)',
                      'İT texniki – təcrübəçi', 'Junior InfoSec Specialist']:
            with self.subTest(title=title):
                self.assertTrue(matches(Job(title, 'Bank'), ROLES, False))
        for title in ['Junior Accountant', 'Information Security Engineer', 'Senior SOC Analyst',
                      'Data üzrə analitik – təcrübəçi', 'Junior Data Analytics / IT',
                      'Internal IT Support', 'Senior IT Support (mentor for interns)']:
            with self.subTest(title=title):
                self.assertFalse(matches(Job(title, 'Bank'), ROLES, False))
        self.assertTrue(matches(Job('Service Desk', 'Bank', employment='Internship'), ROLES, False))
        self.assertFalse(matches(Job('Junior Accountant', 'Bank', description='It is open.'), ROLES, True))

    def test_disk_and_session(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder)/'jobs.db')
            with db:
                db.execute('UPDATE sources SET enabled=(id=1)')
            body = 'Requirements: Windows and networking knowledge.'
            cache = {}
            fetch(db, collector=lambda *_: [Job('Junior Helpdesk', 'Bank', 'https://example.test/1', body)],
                  remember=cache.__setitem__)
            self.assertIn(body, cache.values())
            self.assertEqual(db.execute('SELECT description FROM jobs').fetchone()[0], '')
            with db:
                db.execute("UPDATE runs SET finished='2000-01-01'")
            fetch(db, collector=lambda *_: [])
            self.assertEqual(db.execute('SELECT count(*) FROM identities').fetchone()[0], 0)
            db.close()
