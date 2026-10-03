import unittest
from unittest.mock import MagicMock, patch
import app
from visitflorida_driver import VisitFloridaDriver, PlayerMetadata


class VisitFloridaTests(unittest.TestCase):
    def test_catalog_distance_and_routing(self):
        driver = VisitFloridaDriver()
        nearby = driver.nearby(28.3361, -80.6124, 20)
        self.assertEqual([c['id'] for c in nearby], ['cocoa-beach-pier'])
        self.assertEqual(nearby[0]['catalog_mode'], 'curated')
        self.assertNotIn('url', nearby[0])
        self.assertIn('sebastian-inlet', [c['id'] for c in driver.nearby(28.3361, -80.6124, 50)])
        with patch.dict(app.sources, {'visitflorida': driver}):
            client = app.app.test_client()
            self.assertEqual(client.get('/api/cameras?source=visitflorida').status_code, 200)
            self.assertEqual(client.post('/api/sources/visitflorida/cameras/sebastian-inlet/stream').json['type'], 'image')
            self.assertEqual(client.post('/api/sources/visitflorida/cameras/missing/stream').status_code, 404)

    def test_operator_metadata_and_missing_player(self):
        parser = PlayerMetadata()
        parser.feed('<meta name="twitter:player" content="https://example.com/player?a=1&amp;b=2">')
        self.assertEqual(parser.url, 'https://example.com/player?a=1&b=2')
        parser = PlayerMetadata()
        parser.feed('<meta name="twitter:player" content="http://127.0.0.1/private">')
        self.assertIsNone(parser.url)
        driver = VisitFloridaDriver()
        driver.discover()
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value.text = '<html>No player</html>'
        with patch('visitflorida_driver.http_session', return_value=session):
            with self.assertRaisesRegex(RuntimeError, 'no longer publishes'):
                driver.resolve_stream('englewood-beach')


if __name__ == '__main__':
    unittest.main()
