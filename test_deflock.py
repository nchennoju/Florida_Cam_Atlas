import unittest
from unittest.mock import patch,Mock
from deflock_driver import bearing,normalize,DeFlockDriver,from_feature
import app
class DeFlockTests(unittest.TestCase):
 def test_directions(self):
  for raw,want in [('N',0),('NE',45),('WSW',247.5),('360',0),('123',123),('nan',None),('-1',None),('90-270',None),('unknown',None)]:self.assertEqual(bearing(raw),want)
 def test_metadata(self):
  e={'type':'node','id':1,'lat':28.4,'lon':-80.6,'tags':{'man_made':'surveillance','surveillance:type':'ALPR','direction':'123;NW'}}
  c=normalize(e,'now');self.assertEqual(c['bearings'],[123,315]);self.assertFalse(c['video_available'])
  self.assertEqual(c['page_url'],'https://www.openstreetmap.org/node/1')
  e['tags']['direction']='90-270';self.assertEqual(normalize(e,'now')['bearings'],[])
 def test_geojson_north_and_multiple(self):
  f={'geometry':{'type':'Point','coordinates':[-80.6,28.4]},'properties':{'osmId':1,'osmType':'node','direction':0}}
  self.assertEqual(from_feature(f,'now')['bearings'],[0])
  f['properties']['directions']=[90,270]
  self.assertEqual(from_feature(f,'now')['bearings'],[90,270])
 def test_no_stream(self):
  self.assertEqual(app.app.test_client().post('/api/sources/deflock/cameras/node-1/stream').status_code,400)
if __name__=='__main__':unittest.main()
