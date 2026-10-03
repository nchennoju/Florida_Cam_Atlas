from pathlib import Path
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import app
rows=app.sources['deflock'].nearby(28.336101529243,-80.612406545186,20)
print('Public DeFlock locations within 20 miles:',len(rows),flush=True)
server=make_server('127.0.0.1',8054,app.app,threaded=True)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 with sync_playwright() as p:
  b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':980});errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  for source in ['fl511','opencctv','visitflorida']:page.route('**/api/cameras?source='+source+'*',lambda r:r.fulfill(json={'cameras':[]}))
  page.goto('http://127.0.0.1:8054');page.wait_for_function('sets.deflock.status === "ready"')
  assert page.locator('[data-source=deflock]').count()==len(rows)
  assert page.locator('.alpr-marker').count()==len(rows)
  stream=[];page.on('request',lambda r:stream.append(r.url) if '/stream' in r.url else None)
  page.locator('[data-source=deflock]').first.click()
  assert 'Reported direction:' in page.inner_text('#player-status')
  assert page.locator('#retry').is_hidden();assert not stream
  page.locator('#toggle-deflock').uncheck();assert page.locator('.alpr-marker').count()==0
  assert page.locator('#player-panel').is_hidden()
  page.reload();page.wait_for_function('sets.fl511.status === "ready"');assert not page.locator('#toggle-deflock').is_checked()
  page.locator('#toggle-deflock').check();page.wait_for_function('sets.deflock.status === "ready"')
  page.locator('[data-source=deflock]').first.click()
  page.screenshot(path='test-results/deflock-desktop.png')
  page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  assert not errors,errors
  print('PASS: locations, arrows, details, no stream request, toggle and persistence, mobile',flush=True)
  b.close()
finally:server.shutdown()
