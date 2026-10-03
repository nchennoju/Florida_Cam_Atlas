"""Run: python app.py, then open http://127.0.0.1:8050."""
import argparse
import math
from pathlib import Path

from flask import Flask, jsonify, render_template, request
import requests

from fl511_driver import FL511Driver
from opencctv_driver import OpenCCTVDriver
from visitflorida_driver import VisitFloridaDriver
from deflock_driver import DeFlockDriver

app = Flask(__name__, root_path=str(Path(__file__).resolve().parent))
driver = FL511Driver()
sources = {'fl511': driver, 'opencctv': OpenCCTVDriver(), 'visitflorida': VisitFloridaDriver(), 'deflock': DeFlockDriver()}
DEFAULT_ADDRESS = '123 June Dr, Cocoa Beach, FL 32931'
location_cache = None


def number(name, default, low, high):
    try:
        value = float(request.args.get(name, default))
    except (ValueError, TypeError):
        raise ValueError(f'{name} must be a number.')
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}.')
    return value


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/api/location')
def location():
    global location_cache
    if location_cache:
        return jsonify(location_cache)
    if DEFAULT_ADDRESS == '123 June Dr, Cocoa Beach, FL 32931':
        # Verified with the Census address geocoder; street-address interpolation,
        # not a device GPS fix. Avoid a new geocoding request on every startup.
        return jsonify(lat=28.336101529243, lon=-80.612406545186, approximate=False,
                       label=DEFAULT_ADDRESS + ' · address estimate')
    try:
        response = requests.get('https://geocoding.geo.census.gov/geocoder/locations/onelineaddress',
                                params={'address': DEFAULT_ADDRESS, 'benchmark': 'Public_AR_Current', 'format': 'json'},
                                timeout=(5, 12))
        response.raise_for_status()
        matches = response.json()['result']['addressMatches']
        if not matches:
            raise ValueError('No address match')
        match = matches[0]
        location_cache = {'lat': match['coordinates']['y'], 'lon': match['coordinates']['x'],
                          'label': match['matchedAddress'], 'approximate': False}
        return jsonify(location_cache)
    except (requests.RequestException, ValueError, KeyError):
        return jsonify(lat=28.3200, lon=-80.6100, approximate=True,
                       label='Approximate Cocoa Beach center — address lookup unavailable. Use my location or move the pin.')


@app.get('/api/cameras')
def cameras():
    try:
        source = request.args.get('source', 'fl511')
        if source not in sources:
            return jsonify(error='Unknown camera source.'), 400
        lat = number('lat', 28.32, -90, 90)
        lon = number('lon', -80.61, -180, 180)
        radius = number('radius', 20, 1, 100)
        cameras = sources[source].nearby(lat, lon, radius)
        if source == 'fl511':
            cameras = [{**c, 'source': source, 'provider': 'FDOT', 'feed_type': 'hls',
                        'page_url': 'https://fl511.com/map#camera-' + c['id']} for c in cameras]
        return jsonify(cameras=cameras, source=source)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except (requests.RequestException, RuntimeError, KeyError, TypeError) as exc:
        return jsonify(error=f'Unable to load the camera catalog: {exc}'), 502


@app.post('/api/cameras/<camera_id>/stream')
@app.post('/api/sources/<source>/cameras/<camera_id>/stream')
def stream(camera_id, source='fl511'):
    # No arbitrary names/URLs accepted: resolution is limited to discovered cameras.
    try:
        if source not in sources:
            return jsonify(error='Unknown camera source.'), 404
        if source == 'deflock':
            return jsonify(error='Location-only dataset; no stream is provided.'), 400
        result = sources[source].resolve_stream(camera_id)
        return jsonify(url=result, type='hls') if source == 'fl511' else jsonify(result)
    except KeyError:
        return jsonify(error='Unknown camera. Reload the catalog.'), 404
    except BlockingIOError as exc:
        return jsonify(error=str(exc)), 409
    except Exception as exc:
        app.logger.warning('Stream resolution failed: %s', type(exc).__name__)
        return jsonify(error=str(exc).split('\n')[0]), 502


@app.after_request
def headers(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8050)
    parser.add_argument('--address', default=DEFAULT_ADDRESS)
    args = parser.parse_args()
    DEFAULT_ADDRESS = args.address
    app.run(host='127.0.0.1', port=args.port, threaded=True, debug=False)
