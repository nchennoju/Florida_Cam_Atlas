"""Read-only live catalog check. Does not log visitor keys or save media."""
import json
from collections import Counter
from pathlib import Path
from opencctv_driver import OpenCCTVDriver

if __name__ == '__main__':
    driver = OpenCCTVDriver()
    cameras = driver.nearby(28.336101529243, -80.612406545186, 20)
    print('FLORIDA TOTAL',len(driver.cameras),'NEARBY',len(cameras),flush=True)
    print('FEED TYPES',dict(Counter(c['feed_type'] for c in cameras)),flush=True)
    print(json.dumps([{k:c.get(k) for k in ['id','name','provider','feed_type','distance_miles']} for c in cameras if c['provider'] != 'state511']),flush=True)
    # Ignored test fixture: public metadata only, useful for repeatable UI checks.
    out=Path(__file__).resolve().parent/'test-results'
    out.mkdir(exist_ok=True)
    (out/'opencctv-catalog.json').write_text(json.dumps(list(driver.cameras.values())),encoding='utf-8')
    for kind in ['image','hls','iframe']:
        candidate=next((c for c in cameras if c['feed_type']==kind),None)
        if candidate:
            result=driver.resolve_stream(candidate['id'])
            print('RESOLVED',candidate['name'],result['type'],flush=True)
