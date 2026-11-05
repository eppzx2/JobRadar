import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_jobradar import samples


class Dashboard(unittest.TestCase):
    def test_fetch_button_is_only_network_entry(self):
        calls = []

        def collect(client, source):
            calls.append(source['name'])
            return samples()

        from scraper.workflow import fetch
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, JOBRADAR_DB=tmp+'/db'), \
                patch('frontend.dashboard.fetch', lambda db, progress: fetch(db, progress, collect)):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
            self.assertFalse(calls)
            app.button[0].click().run()
            self.assertEqual(len(calls), 11)
            self.assertEqual([m.value for m in app.metric], ['11','3','2','3','2'])
            app.radio(key='workspace_view').set_value('Sources Management').run()
            self.assertFalse(app.exception)
            app.radio(key='workspace_view').set_value('Keyword Management').run()
            self.assertFalse(app.exception)
            app.radio(key='workspace_view').set_value('All Matching Jobs').run()
            self.assertEqual(len(calls), 11)
            app.button[0].click().run()
            self.assertEqual([m.value for m in app.metric], ['11','3','2','0','0'])
            app.radio(key='workspace_view').set_value('Previously Discovered Jobs').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(calls), 22)
