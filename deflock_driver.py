"""Public OSM ALPR metadata used by DeFlock; no media access."""
import math
import gzip
import json
from pathlib import Path
import time
import threading
from collections import OrderedDict
from datetime import datetime, timezone
import requests
from fl511_driver import distance_miles

COMPASS = dict(zip('N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW'.split(), range(0,360*2,45)))

def bearing(value):
    value = str(value).strip().upper()
    if value in COMPASS:
        return COMPASS[value] / 2
    try:
        number = float(value)
        return number % 360 if math.isfinite(number) and 0 <= number <= 360 else None
    except ValueError:
        return None

def normalize(element, timestamp):
    tags = element.get('tags', {})
    if tags.get('man_made') != 'surveillance' or tags.get('surveillance:type') != 'ALPR':
        return None
    coords = element if element['type'] == 'node' else element.get('center', {})
    try:
        lat, lon = float(coords['lat']), float(coords['lon'])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180): return None
    except (KeyError, ValueError, TypeError): return None
    raw = str(tags.get('camera:direction') if tags.get('camera:direction') is not None else tags.get('direction', ''))
    headings = [bearing(part) for part in raw.split(';')] if raw else []
    headings = list(dict.fromkeys(h for h in headings if h is not None))
    identity = f"{element['type']}/{element['id']}"
    return dict(id=identity.replace('/', '-'), source='deflock',
        name=tags.get('name') or tags.get('description') or 'ALPR camera',
        lat=lat, lon=lon, county=tags.get('addr:city', ''), highway='',
        provider=tags.get('operator') or tags.get('manufacturer') or 'Not reported',
        manufacturer=tags.get('manufacturer', 'Not reported'),
        direction_raw=raw, bearings=headings, check_date=tags.get('check_date', 'Not reported'),
        page_url='https://www.openstreetmap.org/'+identity,
        feed_type='location', video_available=False, catalog_timestamp=timestamp)

DATA_URL = 'https://data.dontgetflocked.com/cameras.geojson.gz'
CACHE = Path(__file__).resolve().parent / 'data' / 'deflock-cache.json'


def from_feature(feature, timestamp):
    props = feature.get('properties', {})
    geometry = feature.get('geometry', {})
    if geometry.get('type') != 'Point' or props.get('osmType') not in ('node', 'way', 'relation'):
        return None
    lon, lat = geometry['coordinates'][:2]
    raw = props.get('directions')
    if isinstance(raw, list):
        raw = ';'.join(str(value) for value in raw)
    else:
        raw = props.get('direction') if props.get('direction') is not None else props.get('directionCardinal', '')
    tags = {'man_made':'surveillance', 'surveillance:type':'ALPR', 'direction':raw,
            'manufacturer':props.get('brand', 'Not reported'), 'operator':props.get('operator', ''),
            'name':(props.get('brand') or 'ALPR')+' camera'+(' · '+props['ref'] if props.get('ref') else '')}
    camera = normalize({'type':props['osmType'], 'id':props['osmId'], 'lat':lat, 'lon':lon,
                        'center':{'lat':lat,'lon':lon}, 'tags':tags}, timestamp)
    if camera: camera['osm_updated'] = props.get('osmTimestamp', 'Unknown')
    return camera


class DeFlockDriver:
    def __init__(self):
        self.rows = []
        self.loaded = 0
        self.lock = threading.Lock()

    def nearby(self, lat, lon, radius):
        with self.lock:
            if not self.loaded or time.monotonic() - self.loaded >= 1800:
                if CACHE.exists() and time.time() - CACHE.stat().st_mtime < 1800:
                    data = json.loads(CACHE.read_text(encoding='utf-8'))
                    fetched = CACHE.stat().st_mtime
                else:
                    response = requests.get(DATA_URL, timeout=(10,60))
                    response.raise_for_status()
                    payload = response.content
                    if payload[:2] == b'\x1f\x8b': payload = gzip.decompress(payload)
                    data = json.loads(payload)
                    fetched = time.time()
                if data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list) or not data['features']:
                    raise RuntimeError('DeFlock returned an invalid or empty dataset.')
                timestamp = datetime.fromtimestamp(fetched, timezone.utc).isoformat()
                rows = [camera for f in data['features'] if (camera := from_feature(f, timestamp))]
                if not rows: raise RuntimeError('No usable DeFlock locations were returned.')
                self.rows, self.loaded = rows, time.monotonic()
        result = []
        # Cheap bounding latitude check before great-circle filtering.
        for camera in self.rows:
            if abs(camera['lat'] - lat) > radius / 68: continue
            distance = distance_miles(lat, lon, camera['lat'], camera['lon'])
            if distance <= radius: result.append({**camera, 'distance_miles':round(distance,2)})
        return sorted(result, key=lambda camera:camera['distance_miles'])
