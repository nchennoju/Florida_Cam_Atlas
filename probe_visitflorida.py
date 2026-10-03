"""Check the new layer with other catalog requests isolated; save no footage."""
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import app

root = Path(__file__).resolve().parent
server = make_server('127.0.0.1', 8051, app.app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width':1440, 'height':980})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for source in ('fl511', 'opencctv', 'deflock'):
            page.route('**/api/cameras?source='+source+'*', lambda route: route.fulfill(json={'cameras':[]}))
        page.goto('http://127.0.0.1:8051')
        page.wait_for_function('sets.visitflorida.status === "ready"')
        assert page.locator('.camera-item[data-source=visitflorida]').count() == 1
        assert page.evaluate('sets.visitflorida.layer.getLayers()[0].options.color') == '#c89aff'
        page.locator('.camera-item[data-source=visitflorida]').click()
        page.wait_for_function('document.querySelector("#embed").hasAttribute("src")')
        page.locator('#toggle-visitflorida').uncheck()
        assert page.locator('#player-panel').is_hidden()
        assert page.locator('#embed').get_attribute('src') is None
        assert page.evaluate('sets.visitflorida.layer.getLayers().length') == 0
        page.reload()
        page.wait_for_function('sets.fl511.status === "ready"')
        assert not page.locator('#toggle-visitflorida').is_checked()
        for source in ('fl511', 'opencctv', 'deflock'):
            page.locator('#toggle-'+source).uncheck()
        assert 'All camera sets are off' in page.locator('#camera-list').inner_text()
        page.locator('#toggle-visitflorida').check()
        page.locator('#radius').select_option('50')
        page.wait_for_function('sets.visitflorida.status === "ready" && sets.visitflorida.cameras.length === 2')
        page.locator('[data-id=sebastian-inlet]').click()
        page.wait_for_function('document.querySelector("#snapshot").naturalWidth > 0', timeout=30000)
        print('PASS: real Sebastian snapshot loaded', flush=True)
        page.locator('#close').click()
        page.screenshot(path=str(root/'test-results'/'visitflorida-desktop.png'))
        page.set_viewport_size({'width':390, 'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(root/'test-results'/'visitflorida-mobile.png'), full_page=True)
        assert not errors, errors
        print('PASS: purple markers, toggle, persisted choice, player cleanup, all-off, radius, mobile', flush=True)
        browser.close()
finally:
    server.shutdown()
