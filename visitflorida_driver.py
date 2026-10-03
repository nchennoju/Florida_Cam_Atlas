"""Curated, source-linked subset of the Florida Now webcam directory.

The directory currently returns HTTP 403 here. Do not imply this manifest is a
complete/live directory import. Operator pages are resolved only on selection.
"""
import json
import math
from html.parser import HTMLParser
from pathlib import Path

from fl511_driver import distance_miles, http_session
from opencctv_driver import public_media_url

DIRECTORY = 'https://www.visitflorida.com/more/florida-now/'
MANIFEST = Path(__file__).resolve().parent / 'data' / 'visitflorida.json'


class PlayerMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and (attrs.get('name') or attrs.get('property')) == 'twitter:player':
            self.url = public_media_url(attrs.get('content'))


class VisitFloridaDriver:
    def __init__(self, manifest=MANIFEST):
        self.manifest = Path(manifest)
        self.cameras = {}

    def discover(self):
        document = json.loads(self.manifest.read_text(encoding='utf-8'))
        cameras = {}
        for entry in document['cameras']:
            lat, lon = float(entry['lat']), float(entry['lon'])
            if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise RuntimeError('Invalid Visit Florida catalog coordinates.')
            if entry['id'] in cameras:
                raise RuntimeError('Duplicate Visit Florida catalog ID.')
            if entry['resolver'] not in ('iframe', 'image', 'earthcam-player'):
                raise RuntimeError('Unsupported Visit Florida resolver.')
            if not public_media_url(entry['url']) or not public_media_url(entry['operator_url']):
                raise RuntimeError('Invalid Visit Florida webcam URL.')
            cameras[entry['id']] = {
                **entry, 'source':'visitflorida', 'lat':lat, 'lon':lon,
                'county':entry['city'], 'highway':'', 'catalog_timestamp':document['reviewed_at'],
                'catalog_mode':'curated', 'catalog_note':document['coverage_note'],
                'directory_url':DIRECTORY, 'page_url':entry['operator_url'],
                'feed_type':'image' if entry['resolver']=='image' else 'iframe',
                'video_available':True,
            }
        if not cameras:
            raise RuntimeError('Visit Florida curated catalog is empty.')
        self.cameras = cameras
        return list(cameras.values())

    def nearby(self, lat, lon, radius):
        result = []
        for camera in self.discover():
            distance = distance_miles(lat, lon, camera['lat'], camera['lon'])
            if distance <= radius:
                result.append({**{key:value for key,value in camera.items() if key not in ('url','resolver')},
                               'distance_miles':round(distance,2)})
        return sorted(result,key=lambda c:(c['distance_miles'],c['name']))

    def resolve_stream(self, camera_id):
        if camera_id not in self.cameras:
            raise KeyError(camera_id)
        camera = self.cameras[camera_id]
        url = camera['url']
        if camera['resolver'] == 'earthcam-player':
            # Use the operator's published social player, not old HLS URLs
            # that require a provider session and can return 403.
            with http_session() as session:
                response = session.get(url, timeout=(10,20))
                response.raise_for_status()
            parser = PlayerMetadata()
            parser.feed(response.text)
            if not parser.url:
                raise RuntimeError('The webcam operator no longer publishes this embedded player. Use Open webcam site.')
            url = parser.url
        return {'url':url, 'type':camera['feed_type'], 'refresh_seconds':60,
                'cache_buster':camera['feed_type']=='image'}
