# Camera Atlas â€” Leaflet first

Local Python app with a Leaflet satellite map, independently selectable FL511, OpenCCTV Florida, and Visit Florida camera sets, a nearby-camera list, and click-to-view video or images. No analytics, recording, or social media integration.

## Run

From this project folder:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Open **http://127.0.0.1:8050**. Existing Microsoft Edge or Chrome can be used instead of installing Chromium. The resolver tries Edge, Chrome, then Playwright Chromium.

The default center is the Census-geocoded street-address estimate for the supplied June Drive address in Cocoa Beach. Drag the blue pin or select **Use my location** to change it. The latter requests browser location permission only when clicked. Choose 5â€“100 miles and filter cameras by name, county, road, provider, or catalog.

**Camera sets:** FL511 uses small teal markers; OpenCCTV uses larger amber rings; Visit Florida uses purple outer rings. Each checkbox independently controls its map markers and list entries, remembers your choice in this browser, and stops the player when its selected set is hidden. All three can be turned off. Dashed or faint markers indicate an unavailable feed. Feed labels distinguish live video, snapshots, image streams, and embedded players. Catalog availability does not guarantee working playback.

OpenCCTV includes FL511 cameras, so both sets can contain the same physical camera. They remain separate entries with source labels; concentric markers keep both visible at matching coordinates. Counts are catalog entries, not deduplicated physical cameras.

Select a marker or list row to request current feed details. **Reconnect** resolves the feed again after a failure or expiration. The source link opens the original camera page. Closing the player stops video, snapshot refreshes, and embedded players. Only one FL511 stream is resolved at a time; a second FL511 request during resolution receives a retry message.

Optional launch settings:

```powershell
python app.py --port 8052 --address "Cocoa Beach, FL"
```

A custom address is sent to the US Census geocoder. Failed lookups are explicitly labeled as an approximate Cocoa Beach center. The default address estimate is built in, so it needs no geocoding request at startup. Edit `DEFAULT_ADDRESS` and the default-coordinate branch in `app.py` if sharing the project without your personal default.

## How it works

- `fl511_driver.py` reads the same public camera catalog used by FL511's camera page, paginates its results, and caches metadata in memory for 30 minutes. Coordinates come from the catalog's WGS84 geometry. Nearby results use great-circle distance.
- Selecting an FL511 camera launches headless Playwright, searches the current FL511 camera page, matches the camera image ID, clicks **Show Video**, and intercepts the generated `.m3u8` request. It prefers `xflow.m3u8`, preserving the method from `test_v8.py`.
- `opencctv_driver.py` uses OpenCCTV's unauthenticated visitor configuration and public list/detail endpoints. It paginates both `Florida` and `FL` state labels, removes inactive/ignored/explicit duplicate records, and caches metadata for 30 minutes. The public visitor key stays in memory and is never logged, saved, or sent to the frontend. No private account or API key is required by this integration.
- OpenCCTV feed details are reloaded on selection. HTTP(S) HLS/MP4, JPEG snapshots, MJPEG streams, and iframe players are supported. IPCamLive aliases use the provider's public embedded player. Other non-web feed schemes are labeled unavailable and retain a source-page link. Snapshots refresh at the provider's advertised rate, bounded to 10â€“300 seconds; loading a snapshot does not establish when the camera captured it.
- `app.py` exposes `/api/cameras?source=fl511|opencctv|visitflorida&lat=...&lon=...&radius=...` and `POST /api/sources/<source>/cameras/<id>/stream`. The older FL511 stream route still works. Browser requests for the catalogs run independently, so an outage in one does not hide the other.
- The browser plays HLS with hls.js or native HLS support. Media is fetched directly by the browser and is not recorded or relayed.
- `static/app.js` renders Leaflet markers over Esri World Imagery, with an optional OpenStreetMap street layer. Leaflet, hls.js, fonts, imagery, and video require internet access.

The catalogs and stream flows are public website interfaces, not guaranteed APIs. Providers can change them. Upstream connection resets are retried a bounded number of times. Offline cameras, expired URLs, blocked video ports, browser codec limits, cross-origin restrictions, or a provider declining iframe embedding can prevent playback. The source-page link remains available. First catalog loading can take longer than subsequent searches. Refresh reloads nearby results from each current 30-minute catalog cache. Disabled sets are loaded only when enabled.

## Checks

```powershell
python test_app.py
python probe.py
python probe_opencctv.py
```

The unit checks cover both catalog adapters, pagination, caching, distance filtering, input validation, source routing, failure isolation, media URL validation, unknown cameras, and failed geocoding. The optional browser smoke check fetches both real catalogs, opens the map in headless Edge on port 8051, checks an OpenCCTV snapshot and FL511 video, and tests toggles, both-off state, media cleanup, remembered preferences, source failure isolation, filtering, and mobile overflow. UI screenshots go under ignored `test-results/`. The standalone OpenCCTV probe also saves a public metadata fixture there; no visitor key is saved.

References: [FL511 camera page](https://fl511.com/cctv), [OpenCCTV](https://opencctv.org/), [Leaflet](https://leafletjs.com/reference.html), [hls.js](https://github.com/video-dev/hls.js), [Census geocoding](https://geocoding.geo.census.gov/), [Esri World Imagery](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer).

## Visit Florida

The purple layer contains eight curated locations listed in [Visit Florida’s Florida Now directory](https://www.visitflorida.com/more/florida-now/). This is not a complete automatic network import: the directory returns HTTP 403 here. `data/visitflorida.json` records the directory reference, approximate coordinates, provider URLs, and metadata references. Some provider links come from OpenCCTV, so entries can overlap. EarthCam players resolve from the public operator page on selection; Sebastian Inlet is a refreshing snapshot. Provider page availability does not guarantee live playback.

Run `python app.py` as before. At the default 20-mile Cocoa Beach radius, Cocoa Beach Pier appears; expand to 50 miles for Sebastian Inlet. Drag the search pin to explore the other locations. `python probe_visitflorida.py` checks the new layer with other catalogs isolated.

Run all unit checks with: python -m unittest test_app test_visitflorida

## Snapchat companion

Use the yellow **Community posts** button. On Snapchat public web content, choose **Share > Embed > Copy code**, paste that code into the panel, and optionally name the post. An official `https://www.snapchat.com/.../embed` URL also works. Ordinary share links should first be opened on Snapchat to obtain its embed code. The panel extracts only the validated embed URL; pasted scripts and HTML are never inserted into the application.

Up to 50 links are saved in this browser's local storage. Select a saved post to load the official player; closing the panel, stopping a post, or removing the selected post unloads it. Camera playback is independent. Posts may expire, require interaction, or be unavailable; the original Snapchat link remains available. Saved labels do not imply verified locations or capture times. No automatic geographic coverage, map overlay, or Snapchat livestream is provided. Snap Map currently requires the mobile app.

Reference: https://developers.snap.com/api/snapchat-for-web/social-plugins/embedding-web-content
Panel browser checks: `python probe_community.py` (mock Snapchat content; no footage saved).

## DeFlock / OSM locations

The pink DeFlock / OSM ALPR toggle displays public camera locations from the US GeoJSON dataset used by https://maps.deflock.org/ (https://data.dontgetflocked.com/cameras.geojson.gz). Each location links to its OSM record. Data is attributed to OpenStreetMap contributors under ODbL. This is community-reported metadata, not a verified inventory or live coverage measurement.

Arrows show numeric/cardinal headings, including multiple headings. Missing, unrecognized, or range-only values show a dot; the original direction value is retained in the details. Arrow size does not imply capture distance or field of view. These entries are location-only and never request a stream. The US dataset is cached in memory for 30 minutes; an optional recent local data/deflock-cache.json avoids startup downloads. Catalog time means retrieval time, not a field verification date. Network failures are isolated from the other sources.

Checks: `python -m unittest test_app test_visitflorida test_deflock` and `python probe_deflock.py`.
