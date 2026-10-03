import unittest
from unittest.mock import patch, Mock, MagicMock

import app
from fl511_driver import Camera, FL511Driver, distance_miles
from opencctv_driver import OpenCCTVDriver, normalize_camera, public_media_url


class CameraTests(unittest.TestCase):
    def test_distance_and_nearby_order(self):
        driver = FL511Driver()
        near = Camera('1', 'Near', 28.336, -80.612, '', '', '', '')
        far = Camera('2', 'Far', 29, -81, '', '', '', '')
        self.assertAlmostEqual(distance_miles(0, 0, 0, 1), 69.0934, places=3)
        with patch.object(driver, 'discover', return_value=[far, near]):
            result = driver.nearby(28.336, -80.612, 20)
        self.assertEqual([c['id'] for c in result], ['1'])

    def test_catalog_pagination_and_atomic_refresh(self):
        def feature(id):
            return {'id': id, 'location': 'Camera', 'latLng': {'geography': {'wellKnownText': 'POINT (-80 28)'}}}
        pages = [Mock(json=lambda: {'data':[feature('1')], 'recordsFiltered':2}),
                 Mock(json=lambda: {'data':[feature('2')], 'recordsFiltered':2})]
        with patch('fl511_driver.requests.Session.get', side_effect=pages) as get:
            driver = FL511Driver()
            self.assertEqual(len(driver.discover()), 2)
            import json
            self.assertEqual(json.loads(get.call_args_list[1].kwargs['params']['query'])['start'], 1)
            driver.discover()
            self.assertEqual(get.call_count, 2)

    def test_invalid_inputs_never_fetch(self):
        client = app.app.test_client()
        with patch.object(app.driver, 'nearby') as nearby:
            for query in ('lat=nan', 'lon=inf', 'radius=0', 'radius=101', 'lat=hello', 'lat=91'):
                self.assertEqual(client.get('/api/cameras?'+query).status_code, 400)
            nearby.assert_not_called()

    def test_unknown_camera(self):
        self.assertEqual(app.app.test_client().post('/api/cameras/not-a-camera/stream').status_code, 404)

    def test_location_failure_is_labelled(self):
        with patch('app.DEFAULT_ADDRESS', 'Different address'), patch('app.requests.get', side_effect=app.requests.ConnectionError):
            result = app.app.test_client().get('/api/location').json
        self.assertTrue(result['approximate'])


class OpenCCTVTests(unittest.TestCase):
    def record(self, id='one', **changes):
        return {'id':id,'country':'US','state':'Florida','active':1,'lat':28.336,'lng':-80.612,
                'name':'Public camera','feed_type':'image','feed_url':'https://example.com/camera.jpg',
                'camera_code':123,'update_rate':30000,**changes}

    def test_normalize_filters_and_feed_types(self):
        camera = normalize_camera(self.record(), 'now')
        self.assertEqual(camera['feed_type'], 'image')
        self.assertEqual(camera['page_url'], 'https://opencctv.org/cam/123')
        for changes in ({'active':0},{'state':'Georgia'},{'lat':float('nan')},{'duplicate_of':'other'},{'ignored':1}):
            self.assertIsNone(normalize_camera(self.record(**changes),'now'))
        self.assertEqual(normalize_camera(self.record(feed_type='m3u8'),'now')['feed_type'],'hls')
        alias_camera=normalize_camera(self.record(feed_type='m3u8',feed_url='ipcamlive://ftolinquad'),'now')
        self.assertEqual(alias_camera['feed_type'],'iframe')
        self.assertIn('alias=ftolinquad',alias_camera['feed_url'])
        for url in ('javascript:alert(1)','http://127.0.0.1/admin','http://localhost:8050/', 'https://user:pass@example.com/x'):
            self.assertIsNone(public_media_url(url))

    def test_both_state_labels_paginated_and_cached(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = [
            Mock(json=lambda: {'total':2,'cameras':[self.record('1')]}),
            Mock(json=lambda: {'total':2,'cameras':[self.record('2')]}),
            Mock(json=lambda: {'total':1,'cameras':[self.record('3',state='FL')]}),
        ]
        driver = OpenCCTVDriver()
        with patch.object(driver,'_visitor_session',return_value=session):
            self.assertEqual(len(driver.discover()),3)
            self.assertEqual(session.get.call_args_list[1].kwargs['params']['page'],2)
            self.assertEqual(session.get.call_args_list[2].kwargs['params']['state'],'FL')
            self.assertEqual(len(driver.nearby(28.336,-80.612,1)),3)
            self.assertNotIn('feed_url',driver.nearby(28.336,-80.612,1)[0])
            self.assertEqual(session.get.call_count,3)

    def test_repeated_page_does_not_replace_existing_catalog(self):
        session = MagicMock()
        session.__enter__.return_value=session
        session.get.return_value=Mock(json=lambda: {'total':2,'cameras':[self.record('1')]})
        driver=OpenCCTVDriver()
        driver.cameras={'old':normalize_camera(self.record('old'),'before')}
        with patch.object(driver,'_visitor_session',return_value=session):
            with self.assertRaisesRegex(RuntimeError,'incomplete'):
                driver.discover()
        self.assertIn('old',driver.cameras)

    def test_source_routing_and_failure_isolation(self):
        fl = Mock(nearby=Mock(side_effect=RuntimeError('FL511 offline')))
        oc = Mock(nearby=Mock(return_value=[{'id':'one','source':'opencctv'}]),
                  resolve_stream=Mock(return_value={'type':'image','url':'https://example.com/a.jpg'}))
        with patch.dict(app.sources,{'fl511':fl,'opencctv':oc}):
            client=app.app.test_client()
            self.assertEqual(client.get('/api/cameras?source=fl511').status_code,502)
            response=client.get('/api/cameras?source=opencctv')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['cameras'][0]['source'],'opencctv')
            self.assertEqual(client.post('/api/sources/opencctv/cameras/one/stream').json['type'],'image')
            oc.resolve_stream.assert_called_once_with('one')
            self.assertEqual(client.get('/api/cameras?source=unknown').status_code,400)
            self.assertEqual(client.post('/api/sources/unknown/cameras/one/stream').status_code,404)


if __name__ == '__main__':
    unittest.main()
