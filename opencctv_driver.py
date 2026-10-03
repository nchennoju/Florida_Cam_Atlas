"""OpenCCTV's Florida public catalog and fresh feed metadata."""
from datetime import datetime, timezone
import ipaddress
import math
import re
import threading
import time
from urllib.parse import quote, urlsplit

from fl511_driver import distance_miles, http_session

BASE = 'https://opencctv.org'


def public_media_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password:
            return None
        if host == 'localhost' or '.' not in host or host.endswith(('.localhost', '.local', '.internal')):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return value
    except ValueError:
        return None


def normalize_camera(record, fetched):
    if record.get('country') not in ('US', 'USA') or str(record.get('state') or '').lower() not in ('fl', 'florida'):
        return None
    if record.get('active') not in (1, True, '1') or record.get('ignored') or record.get('duplicate_of'):
        return None
    try:
        lat, lon = float(record['lat']), float(record['lng'])
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
    except (KeyError, ValueError, TypeError):
        return None
    camera_id = str(record['id'])
    code = str(record.get('camera_code') or '')
    media_type = {'m3u8': 'hls', 'hls': 'hls', 'image': 'image', 'jpeg': 'image',
                  'mjpeg': 'mjpeg', 'iframe': 'iframe', 'mp4': 'mp4'}.get(record.get('feed_type'), 'unsupported')
    feed_url = public_media_url(record.get('feed_url'))
    alias = re.fullmatch(r'ipcamlive://([A-Za-z0-9_-]{1,100})', str(record.get('feed_url') or ''))
    if alias:
        # Use the provider's normal public player, which manages stream rotation.
        feed_url = 'https://g1.ipcamlive.com/player/player.php?alias=' + alias[1]
        media_type = 'iframe'
    try:
        refresh_seconds = float(record.get('update_rate') or 30000) / 1000
        if not math.isfinite(refresh_seconds):
            refresh_seconds = 30
    except (ValueError, TypeError):
        refresh_seconds = 30
    return {'id': camera_id, 'source': 'opencctv', 'name': record.get('name') or camera_id,
            'lat': lat, 'lon': lon, 'county': record.get('city') or 'Florida', 'highway': '',
            'catalog_timestamp': fetched, 'provider': record.get('source') or 'OpenCCTV',
            'feed_type': media_type, 'video_available': bool(feed_url) and media_type != 'unsupported',
            'page_url': f'{BASE}/cam/{code}' if code.isdigit() else BASE,
            'last_checked': record.get('last_checked'), 'feed_url': feed_url,
            'refresh_seconds': max(10, min(300, refresh_seconds)),
            'cache_buster': not bool(record.get('cache_buster_breaks_url'))}


class OpenCCTVDriver:
    def __init__(self):
        self.cameras = {}
        self.loaded_at = 0
        self.catalog_lock = threading.Lock()

    @staticmethod
    def _visitor_session():
        session = http_session()
        try:
            response = session.get(BASE + '/api/config', timeout=(10, 20))
            response.raise_for_status()
            # Public visitor key distributed to the site's unauthenticated client.
            # This is not an account token; never log or persist it.
            key = response.json().get('fk')
            if not key:
                raise RuntimeError('OpenCCTV public visitor configuration is unavailable.')
            session.headers['X-Feed-Key'] = key
            return session
        except Exception:
            session.close()
            raise

    def discover(self):
        with self.catalog_lock:
            if self.cameras and time.monotonic() - self.loaded_at < 1800:
                return list(self.cameras.values())
            fetched = datetime.now(timezone.utc).isoformat(timespec='seconds')
            cameras = {}
            with self._visitor_session() as session:
                # Both labels occur in the actual catalog; limiting to only one
                # silently omits either most traffic cams or many beach cams.
                for state in ('Florida', 'FL'):
                    page, received = 1, 0
                    seen_ids = set()
                    while True:
                        response = session.get(BASE + '/api/cameras/list', params={
                            'country': 'US', 'state': state, 'page': page, 'limit': 100,
                            'sortBy': 'name', 'sortDir': 'asc',
                        }, timeout=(10, 30))
                        response.raise_for_status()
                        payload = response.json()
                        if not isinstance(payload.get('cameras'), list) or 'total' not in payload:
                            raise RuntimeError('OpenCCTV returned an unexpected catalog format.')
                        records = payload['cameras']
                        ids = {str(item.get('id')) for item in records}
                        if received < payload['total'] and (not records or ids <= seen_ids):
                            raise RuntimeError('OpenCCTV returned an incomplete catalog page.')
                        seen_ids.update(ids)
                        for record in records:
                            camera = normalize_camera(record, fetched)
                            if camera:
                                cameras[camera['id']] = camera
                        received += len(records)
                        if received >= payload['total']:
                            break
                        page += 1
                        if page > 200:
                            raise RuntimeError('OpenCCTV catalog exceeded its expected Florida page count.')
            if not cameras:
                raise RuntimeError('OpenCCTV did not return any active Florida cameras.')
            self.cameras, self.loaded_at = cameras, time.monotonic()
            return list(cameras.values())

    def nearby(self, lat, lon, radius):
        result = []
        for camera in self.discover():
            distance = distance_miles(lat, lon, camera['lat'], camera['lon'])
            if distance <= radius:
                # Keep actual feed URLs out of catalog responses; resolve on click.
                public = {k: v for k, v in camera.items() if k != 'feed_url'}
                result.append({**public, 'distance_miles': round(distance, 2)})
        return sorted(result, key=lambda camera: (camera['distance_miles'], camera['name']))

    def resolve_stream(self, camera_id):
        if camera_id not in self.cameras:
            raise KeyError(camera_id)
        with self._visitor_session() as session:
            response = session.get(BASE + '/api/cameras/' + quote(camera_id, safe=''), timeout=(10, 20))
            response.raise_for_status()
            camera = normalize_camera(response.json(), datetime.now(timezone.utc).isoformat(timespec='seconds'))
        if not camera or not camera['video_available']:
            raise RuntimeError('This OpenCCTV feed is unavailable or requires its original player.')
        return {'url': camera['feed_url'], 'type': camera['feed_type'],
                'refresh_seconds': camera['refresh_seconds'], 'cache_buster': camera['cache_buster']}
