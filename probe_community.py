from pathlib import Path
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import app
server=make_server('127.0.0.1',8053,app.app,threaded=True)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='msedge',headless=True)
  page=browser.new_page(viewport={'width':1600,'height':1000})
  errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/cameras?*',lambda r:r.fulfill(json={'cameras':[]}))
  page.route('https://www.snapchat.com/**',lambda r:r.fulfill(content_type='text/html',body='<p>Test public post player</p>'))
  page.goto('http://127.0.0.1:8053'); page.click('#community-toggle')
  page.fill('#community-code','https://evil.example/test/embed');page.click('#community-form button')
  assert 'Use Snapchat' in page.inner_text('#community-status')
  assert page.locator('#community-frame').get_attribute('src') is None
  page.fill('#community-title','Beach conditions')
  page.fill('#community-code','<blockquote data-snapchat-embed-url="https://www.snapchat.com/spotlight/test/embed"></blockquote><script>window.injected=true</script>')
  page.click('#community-form button')
  assert not page.evaluate('!!window.injected')
  assert page.locator('.community-row').count()==1
  assert page.locator('#community-frame').get_attribute('src').endswith('/embed')
  page.click('#community-close');assert page.locator('#community-frame').get_attribute('src') is None
  page.reload();page.click('#community-toggle');assert page.locator('.community-row').count()==1
  page.click('.community-row button:first-child')
  page.screenshot(path='test-results/community-desktop.png')
  page.set_viewport_size({'width':390,'height':844})
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  page.screenshot(path='test-results/community-mobile.png')
  page.click('.community-row button.secondary');assert page.locator('.community-row').count()==0
  assert page.locator('#community-frame').get_attribute('src') is None
  assert not errors,errors
  print('PASS: URL rejection, inert embed parsing, save/reload, close/remove media cleanup, desktop/mobile',flush=True)
  browser.close()
finally:server.shutdown()
