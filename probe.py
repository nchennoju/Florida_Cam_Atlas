"""Manual end-to-end check against public services. No footage is saved."""
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import json
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import app

root=Path(__file__).resolve().parent
app.location_cache={'lat':28.336101529243,'lon':-80.612406545186,'label':'123 June Dr, Cocoa Beach, FL 32931 (address estimate)','approximate':False}
with ThreadPoolExecutor(max_workers=2) as pool:
    results = dict(zip(app.sources,pool.map(lambda source: source.nearby(28.336101529243,-80.612406545186,20),app.sources.values())))
cameras=results['fl511']
oc_cameras=results['opencctv']
print('NEARBY', {source:len(rows) for source,rows in results.items()}, flush=True)
chosen=next(c for c in cameras if c['video_available'])
print('TEST CAMERA',chosen['id'],chosen['name'],flush=True)
server=make_server('127.0.0.1',8051,app.app,threaded=True)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':980})
        errors=[]
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:8051',wait_until='domcontentloaded')
        page.wait_for_function('Object.values(sets).every(s=>s.status === "ready")',timeout=30000)
        total=sum(len(rows) for rows in results.values())
        assert page.locator('.camera-item').count()==total
        # Each switch controls both the map layer and list, and can be restored.
        page.locator('#toggle-fl511').uncheck()
        assert page.locator('.camera-item[data-source=fl511]').count()==0
        assert page.evaluate('sets.fl511.layer.getLayers().length')==0
        assert page.locator('.camera-item').count()==len(oc_cameras)+len(results['visitflorida'])+len(results['deflock'])
        page.locator('#toggle-opencctv').uncheck()
        page.locator('#toggle-visitflorida').uncheck()
        page.locator('#toggle-deflock').uncheck()
        assert page.locator('.camera-item').count()==0
        assert 'All camera sets are off' in page.locator('#camera-list').inner_text()
        page.locator('#toggle-fl511').check()
        assert page.locator('.camera-item').count()==len(cameras)
        page.locator('#toggle-opencctv').check()
        page.locator('#toggle-visitflorida').check()
        page.locator('#toggle-deflock').check()
        assert page.locator('.camera-item').count()==total
        image_camera=next(c for c in oc_cameras if c['feed_type']=='image' and c['provider']!='state511')
        page.locator(f'.camera-item[data-source="opencctv"][data-id="{image_camera["id"]}"]').click()
        page.wait_for_function('document.querySelector("#player-status").textContent.startsWith("Snapshot loaded") || document.querySelector("#player-status").textContent.includes("could not")',timeout=40000)
        print('OPENCCTV IMAGE',page.locator('#player-status').inner_text(),flush=True)
        assert page.locator('#snapshot').evaluate('(img)=>img.naturalWidth>0')
        (root/'test-results').mkdir(exist_ok=True)
        page.screenshot(path=str(root/'test-results'/'opencctv-desktop.png'))
        # Disabling the selected set must stop its media, not merely hide markers.
        page.locator('#toggle-opencctv').uncheck()
        assert page.locator('#player-panel').is_hidden()
        assert page.locator('#snapshot').get_attribute('src') is None
        page.locator('#toggle-opencctv').check()
        page.wait_for_function('Array.from(document.querySelectorAll(".leaflet-tile-loaded")).length > 2')
        page.locator(f'.camera-item[data-source="fl511"][data-id="{chosen["id"]}"]').click()
        page.wait_for_function('document.querySelector("#player-status").textContent.startsWith("Playing live") || document.querySelector("#retry").disabled === false',timeout=150000)
        page.wait_for_timeout(15000)
        print('PLAYER',page.locator('#player-status').inner_text(),flush=True)
        print('VIDEO',page.locator('video').evaluate('(v)=>({ready:v.readyState,time:v.currentTime,width:v.videoWidth,height:v.videoHeight})'),flush=True)
        assert page.locator('video').evaluate('(v)=>v.videoWidth>0 && v.currentTime>0')
        print('JS ERRORS',errors,flush=True)
        print('TILES',page.locator('.leaflet-tile').evaluate_all('(tiles)=>({total:tiles.length,loaded:tiles.filter(t=>t.complete&&t.naturalWidth>0).length})'),flush=True)
        (root/'test-results').mkdir(exist_ok=True)
        page.screenshot(path=str(root/'test-results'/'desktop.png'))
        page.locator('#close').click()
        page.locator('#filter').fill('no such camera')
        assert page.locator('.camera-item').count()==0
        page.locator('#filter').fill('')
        assert page.locator('.camera-item').count()==total
        # Source failure is isolated; FL511 remains usable.
        page.route('**/api/cameras?source=opencctv*',lambda route: route.fulfill(status=502,content_type='application/json',body=json.dumps({'error':'Test outage'})))
        page.locator('#refresh').click()
        page.wait_for_function('sets.opencctv.status === "error" && sets.fl511.status === "ready"')
        assert page.locator('.camera-item[data-source=fl511]').count()==len(cameras)
        page.unroute('**/api/cameras?source=opencctv*')
        page.locator('#refresh').click()
        page.wait_for_function('Object.values(sets).every(s=>s.status === "ready")')
        page.locator('#toggle-fl511').uncheck()
        page.reload(wait_until='domcontentloaded')
        page.wait_for_function('sets.opencctv.status === "ready"')
        assert not page.locator('#toggle-fl511').is_checked()
        assert page.locator('.camera-item[data-source=fl511]').count()==0
        page.locator('#toggle-fl511').check()
        page.wait_for_function('sets.fl511.status === "ready"')
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(700)
        page.screenshot(path=str(root/'test-results'/'mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        print('PASS: both toggles, both off, media cleanup, persisted choice, source failure isolation, filtering, mobile, FL511 video, OpenCCTV snapshot',flush=True)
        browser.close()
finally:
    server.shutdown()
