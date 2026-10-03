"""Public FL511 discovery and on-demand HLS resolution. No video analytics."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import re
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright

CATALOG = 'https://fl511.com/List/GetData/Cameras'
CCTV_PAGE = 'https://fl511.com/cctv?start=0&length=500&order%5Bi%5D=1&order%5Bdir%5D=asc'


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    lat: float
    lon: float
    county: str
    highway: str
    direction: str
    catalog_timestamp: str
    video_available: bool = True
    image_id: str = ''


def distance_miles(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return 3958.7613 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def http_session():
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=.5,
                   status_forcelist=[500, 502, 503, 504])))
    return session


class FL511Driver:
    def __init__(self):
        self.cameras = {}
        self.loaded_at = 0
        self.catalog_lock = threading.Lock()
        self.resolve_lock = threading.Lock()

    def discover(self):
        with self.catalog_lock:
            if self.cameras and time.monotonic() - self.loaded_at < 1800:
                return list(self.cameras.values())
            cameras = {}
            offset = 0
            fetched = datetime.now(timezone.utc).isoformat(timespec='seconds')
            with http_session() as session:
                while True:
                    query = {'columns': [{'data': None, 'name': ''},
                             *[{'name': name, 's': True} for name in ('sortOrder', 'region', 'county', 'roadway')],
                             {'name': 'location'}, {'name': 'direction', 's': True},
                             {'data': 7, 'name': ''}],
                             'order': [{'column': 1, 'dir': 'asc'}, {'column': 2, 'dir': 'asc'}],
                             'start': offset, 'length': 500, 'search': {'value': ''}}
                    response = session.get(CATALOG, params={'query': json.dumps(query, separators=(',', ':')), 'lang': 'en-US'}, timeout=(10, 30))
                    response.raise_for_status()
                    payload = response.json()
                    if 'data' not in payload or 'recordsFiltered' not in payload:
                        raise RuntimeError('FL511 returned an unexpected catalog format.')
                    records = payload['data']
                    for item in records:
                        wkt = ((item.get('latLng') or {}).get('geography') or {}).get('wellKnownText', '')
                        match = re.fullmatch(r'POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)', wkt)
                        if not match:
                            continue
                        lon, lat = map(float, match.groups())
                        playable = [image for image in item.get('images', []) if image.get('videoUrl')
                                    and not any(image.get(flag) for flag in ('videoDisabled', 'disabled', 'blocked'))]
                        camera = Camera(str(item['id']), item.get('location') or f"Camera {item['id']}",
                                        lat, lon, item.get('county') or '', item.get('roadway') or '',
                                        item.get('direction') or '', fetched, bool(playable),
                                        str(playable[0]['id']) if playable else '')
                        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
                            cameras[camera.id] = camera
                    offset += len(records)
                    if offset >= payload['recordsFiltered']:
                        break
                    if not records:
                        raise RuntimeError('Camera catalog pagination returned an incomplete result.')
            if not cameras:
                raise RuntimeError('The camera catalog is empty. Please retry later.')
            self.cameras = cameras
            self.loaded_at = time.monotonic()
            return list(cameras.values())

    def nearby(self, lat, lon, radius):
        results = []
        for camera in self.discover():
            distance = distance_miles(lat, lon, camera.lat, camera.lon)
            if distance <= radius:
                results.append({**asdict(camera), 'distance_miles': round(distance, 2)})
        return sorted(results, key=lambda c: (c['distance_miles'], c['name']))

    def resolve_stream(self, camera_id):
        camera = self.cameras.get(camera_id)
        if camera is None:
            raise KeyError(camera_id)
        if not camera.video_available:
            raise RuntimeError('FL511 currently marks this camera video as unavailable. Try another camera.')
        if not self.resolve_lock.acquire(blocking=False):
            raise BlockingIOError('Another camera is being resolved. Please retry in a few seconds.')
        try:
            return self._resolve(camera)
        finally:
            self.resolve_lock.release()

    @staticmethod
    def _resolve(camera):
        # Adapted from test_v8.py: let FL511 create its current signed HLS URL.
        with sync_playwright() as p:
            browser = None
            for channel in ('msedge', 'chrome', None):
                try:
                    browser = p.chromium.launch(headless=True, **({'channel': channel} if channel else {}))
                    break
                except Exception:
                    continue
            if browser is None:
                raise RuntimeError('Install a browser: python -m playwright install chromium')
            try:
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                for attempt in range(3):
                    try:
                        page.goto(CCTV_PAGE, wait_until='domcontentloaded', timeout=30000)
                        page.locator('tbody .locationTitle').first.wait_for(timeout=20000)
                        break
                    except Exception:
                        if attempt == 2:
                            raise RuntimeError('FL511 could not be reached. Please retry shortly.')
                        page.wait_for_timeout(1000)
                search = page.locator('input[type="search"]').first
                search.wait_for(timeout=20000)
                search.fill(camera.name)
                page.wait_for_timeout(3000)
                rows = page.locator('tbody tr')
                matches = []
                for index in range(rows.count()):
                    row = rows.nth(index)
                    if row.get_by_text('Show Video', exact=False).count() == 0:
                        continue
                    # The catalog ID matches the current public card's ID.
                    buttons = row.locator('button.showVideo')
                    if any(buttons.nth(i).get_attribute('data-camera-id') == (camera.image_id or camera.id)
                           for i in range(buttons.count())):
                        matches.append(row)
                if len(matches) != 1:
                    raise RuntimeError('Could not uniquely match this catalog camera on FL511. It may have been renamed or removed.')
                captured = []
                page.on('request', lambda request: captured.append(request.url)
                        if '.m3u8' in request.url.lower() else None)
                buttons = matches[0].locator('button.showVideo')
                for index in range(buttons.count()):
                    if buttons.nth(index).get_attribute('data-camera-id') == (camera.image_id or camera.id):
                        buttons.nth(index).click(timeout=10000)
                        break
                deadline = time.monotonic() + 25
                first_seen = None
                while time.monotonic() < deadline:
                    page.wait_for_timeout(250)
                    preferred = next((url for url in captured if 'xflow.m3u8' in url.lower()), None)
                    if preferred:
                        return preferred
                    if captured:
                        first_seen = first_seen or time.monotonic()
                        if time.monotonic() - first_seen >= 2:
                            return captured[0]
                raise RuntimeError('FL511 did not provide a live stream. The camera may be offline; try again later.')
            finally:
                browser.close()
