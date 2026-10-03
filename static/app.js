'use strict';
const $ = id => document.getElementById(id);
const sets = {
  fl511: {label:'FL511', color:'#29c8ad', cameras:[], status:'idle', enabled:true},
  opencctv: {label:'OpenCCTV', color:'#ffba57', cameras:[], status:'idle', enabled:true},
  deflock: {label:'DeFlock / OSM', color:'#ff8291', cameras:[], status:'idle', enabled:true},
  visitflorida: {label:'Visit Florida', color:'#c89aff', cameras:[], status:'idle', enabled:true}
};
let map, origin, radiusCircle, cameras = [], selected = null;
let hls = null, imageTimer = null, selectionVersion = 0, catalogVersion = 0;
let center = [28.336101529243, -80.612406545186];
const video = $('video'), snapshot = $('snapshot'), embed = $('embed');
const cameraKey = camera => `${camera.source}:${camera.id}`;
const feedLabel = camera => camera.source === 'deflock' ? 'Location only' : !camera.video_available ? 'Unavailable' :
  ({hls:'Live video',image:'Snapshot',mjpeg:'Image stream',iframe:'Embedded player',mp4:'Video'}[camera.feed_type] || 'Original player');

async function json(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function stopVideo() {
  clearTimeout(imageTimer); imageTimer = null;
  if (hls) { hls.destroy(); hls = null; }
  video.pause(); video.removeAttribute('src'); video.load(); video.hidden = true;
  snapshot.onload = null; snapshot.onerror = null; snapshot.removeAttribute('src'); snapshot.hidden = true;
  embed.onload = null; embed.removeAttribute('src'); embed.hidden = true;
}

function closePlayer() {
  ++selectionVersion; selected = null; stopVideo(); $('player-panel').hidden = true;
  document.querySelectorAll('.camera-item.selected').forEach(row => row.classList.remove('selected'));
}

async function selectCamera(camera) {
  selected = camera;
  const version = ++selectionVersion;
  stopVideo();
  $('player-panel').hidden = false;
  $('camera-title').textContent = camera.name;
  $('player-source').textContent = `${sets[camera.source].label} · ${feedLabel(camera)}`;
  $('player-source').style.color = sets[camera.source].color;
  $('camera-detail').textContent = `${camera.county} · ${camera.distance_miles.toFixed(1)} mi · Provider: ${camera.provider} · ${camera.catalog_mode === 'curated' ? 'Curated catalog reviewed' : 'Catalog'}: ${new Date(camera.catalog_timestamp).toLocaleString()}${camera.location_note ? ' · '+camera.location_note : ''}`;
  $('original').href = camera.page_url;
  $('original').textContent = camera.source === 'visitflorida' ? 'Open webcam site ↗' : `View on ${sets[camera.source].label} ↗`;
  $('player-status').textContent = camera.source === 'fl511' ?
    'Requesting a fresh stream from FL511… This can take up to a minute.' : `Loading camera player from ${sets[camera.source].label}…`;
  $('retry').hidden = camera.source === 'deflock';
  if (camera.source === 'deflock') {
    $('original').textContent = 'View OSM record ↗';
    $('player-status').textContent = `Reported direction: ${camera.direction_raw || 'Unknown'}. Arrows show reported headings, not measured coverage or range. No stream is provided.`;
    $('camera-detail').textContent += ` · Manufacturer: ${camera.manufacturer} · Last checked: ${camera.check_date} · Community-reported location and direction may be incomplete or outdated.`;
    return;
  }
  $('retry').disabled = true;
  document.querySelectorAll('.camera-item').forEach(el => el.classList.toggle('selected', el.dataset.key === cameraKey(camera)));
  try {
    const data = await json(`/api/sources/${camera.source}/cameras/${encodeURIComponent(camera.id)}/stream`, {method:'POST'});
    if (version !== selectionVersion) return;
    if (data.type === 'image' || data.type === 'mjpeg') {
      const refresh = () => {
        if(version !== selectionVersion) return;
        const url = new URL(data.url);
        if(data.cache_buster && data.type === 'image') url.searchParams.set('_atlas', Date.now());
        snapshot.src = url.toString();
      };
      snapshot.hidden = false;
      snapshot.onload = () => {
        if(version !== selectionVersion) return;
        $('player-status').textContent = data.type === 'mjpeg' ? 'Image stream connected' :
          `Snapshot loaded at ${new Date().toLocaleTimeString()} · refresh every ${data.refresh_seconds}s`;
        if(data.type === 'image') {clearTimeout(imageTimer); imageTimer = setTimeout(refresh, data.refresh_seconds * 1000);}
      };
      snapshot.onerror = () => {
        if(version !== selectionVersion) return;
        clearTimeout(imageTimer); snapshot.hidden = true;
        $('player-status').textContent = 'The image could not load. Retry or open the original camera.';
      };
      $('player-status').textContent = 'Loading camera image…';
      refresh();
      return;
    }
    if(data.type === 'iframe') {
      embed.hidden = false;
      embed.onload = () => {if(version === selectionVersion) $('player-status').textContent = 'Original embedded player · press Play if needed. If blocked, use the source link.';};
      embed.src = data.url;
      $('player-status').textContent = 'Opening the embedded camera player…';
      return;
    }
    video.hidden = false;
    $('player-status').textContent = 'Connecting to live video…';
    if(data.type === 'mp4') video.src = data.url;
    else if (window.Hls && Hls.isSupported()) {
      hls = new Hls({maxBufferLength:15});
      hls.on(Hls.Events.ERROR, (_, error) => {
        if (error.fatal && version === selectionVersion) {
          $('player-status').textContent = 'Playback failed or the feed expired. Reconnect, or open the original camera.';
          stopVideo();
        }
      });
      hls.loadSource(data.url); hls.attachMedia(video);
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) video.src = data.url;
    else throw new Error('This browser cannot play HLS video. Open the original camera.');
    video.play().catch(() => {if(version === selectionVersion) $('player-status').textContent = 'Press Play to start the feed.';});
  } catch (error) {
    if (version === selectionVersion) $('player-status').textContent = error.message;
  } finally {if(version === selectionVersion) $('retry').disabled = false;}
}

function renderCameras() {
  for(const [id,set] of Object.entries(sets)) {
    set.layer.clearLayers();
    const status = $('source-status-'+id);
    status.textContent = set.status === 'loading' ? 'Loading…' : set.status === 'error' ? `Unavailable: ${set.error}` :
      set.status === 'ready' ? `${set.cameras.length} nearby${id === 'visitflorida' ? ' · curated' : ''}${set.enabled ? '' : ' · hidden'}` : 'Off · enable to load';
    status.title = set.error || status.textContent;
    status.classList.toggle('error',set.status === 'error');
  }
  cameras = Object.values(sets).filter(set => set.enabled).flatMap(set => set.cameras)
    .sort((a,b) => a.distance_miles-b.distance_miles || a.name.localeCompare(b.name) || a.source.localeCompare(b.source));
  $('camera-list').replaceChildren();
  const query = $('filter').value.trim().toLowerCase();
  const filtered = cameras.filter(c => `${c.name} ${c.county} ${c.highway} ${sets[c.source].label} ${c.provider}`.toLowerCase().includes(query));
  const enabled = Object.values(sets).filter(set => set.enabled);
  const loading = enabled.some(set => set.status === 'loading');
  $('catalog-status').textContent = `${filtered.length} entries · nearest first · within ${$('radius').value} mi${loading ? ' · loading…' : ''}`;
  for (const camera of filtered) {
    const set = sets[camera.source], ring = camera.source !== 'fl511';
    const tooltip = document.createElement('span'); tooltip.textContent = `${set.label} · ${camera.name} · ${feedLabel(camera)}`;
    if (camera.source === 'deflock') {
      const arrows = camera.bearings.map(angle => `<path d="M24 24 L24 3 M19 9 L24 3 L29 9" transform="rotate(${angle} 24 24)"/>`).join('');
      const html = `<svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="#ff8291" stroke-width="3">${arrows}<circle cx="24" cy="24" r="6" fill="#522837"/></svg>`;
      L.marker([camera.lat,camera.lon], {pane:'deflock',icon:L.divIcon({className:'alpr-marker',html,iconSize:[48,48],iconAnchor:[24,24]})}).addTo(set.layer).bindTooltip(tooltip).on('click',()=>selectCamera(camera));
    } else L.circleMarker([camera.lat,camera.lon], {pane:camera.source,radius:camera.source === 'visitflorida' ? 14 : ring ? 10 : 5.5,
      color:ring ? set.color : '#defff7',weight:ring ? 2.5 : 1.5,fillColor:set.color,
      fillOpacity:ring ? .12 : camera.video_available ? .95 : .2,
      dashArray:camera.video_available ? null : '2 3'})
      .addTo(set.layer).bindTooltip(tooltip).on('click', () => selectCamera(camera));
    const row = document.createElement('button'); row.className = 'camera-item';
    row.dataset.id = camera.id; row.dataset.source = camera.source; row.dataset.key = cameraKey(camera);
    row.style.setProperty('--source-color',set.color);
    row.classList.toggle('selected',selected && cameraKey(selected) === cameraKey(camera));
    const glyph = document.createElement('span'); glyph.className = 'camera-glyph'; glyph.textContent = ring ? '◎' : '◉';
    const label = document.createElement('span');
    const name = document.createElement('strong'); name.textContent = camera.name;
    const detail = document.createElement('small'); detail.textContent = `${set.label} · ${feedLabel(camera)}`;
    label.append(name,detail);
    const distance = document.createElement('span'); distance.className = 'distance'; distance.textContent = `${camera.distance_miles.toFixed(1)} mi`;
    row.append(glyph,label,distance);
    row.onclick = () => {map.panTo([camera.lat,camera.lon]); selectCamera(camera);};
    $('camera-list').append(row);
  }
  if(!filtered.length) {
    const empty = document.createElement('p'); empty.className = 'empty';
    empty.textContent = !enabled.length ? 'All camera sets are off. Enable a set above to show its cameras.' : loading ? 'Fetching nearby cameras…' :
      query ? 'No cameras match your filter.' : enabled.every(set => set.status === 'error') ? 'The selected catalogs could not load. Press Refresh to retry.' :
      'No cameras in the selected sets within this radius. Try expanding the search.';
    $('camera-list').append(empty);
  }
}

async function loadSource(id, version) {
  const set = sets[id]; set.status = 'loading'; set.error = '';
  renderCameras();
  try {
    const data = await json(`/api/cameras?source=${id}&lat=${center[0]}&lon=${center[1]}&radius=${$('radius').value}`);
    if(version !== catalogVersion) return;
    set.cameras = data.cameras; set.status = 'ready';
  } catch(error) {
    if(version !== catalogVersion) return;
    set.status = 'error'; set.error = error.message;
  }
  renderCameras();
}

async function loadCameras(fit = false) {
  const version = ++catalogVersion;
  closePlayer();
  radiusCircle.setLatLng(center).setRadius(Number($('radius').value)*1609.344);
  origin.setLatLng(center);
  if(fit) map.fitBounds(radiusCircle.getBounds(), {padding:[20,20],maxZoom:13});
  for(const set of Object.values(sets)) {set.cameras=[]; set.status='idle'; set.error='';}
  renderCameras();
  await Promise.all(Object.entries(sets).filter(([,set]) => set.enabled).map(([id]) => loadSource(id,version)));
}

async function init() {
  if(!window.L) {$('catalog-status').textContent='Leaflet could not load. Check your internet connection and reload.'; return;}
  map = L.map('map', {zoomControl:false}).setView(center,12);
  L.control.zoom({position:'topright'}).addTo(map);
  const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom:19,attribution:'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
  }).addTo(map);
  satellite.on('tileerror', event => {
    const tile=event.tile, retries=Number(tile.dataset.retries || 0);
    if(retries >= 3) return;
    tile.dataset.retries=String(retries+1);
    setTimeout(() => {
      if(!tile.isConnected) return;
      const url=new URL(tile.src); url.hostname=retries%2===0 ? 'services.arcgisonline.com' : 'server.arcgisonline.com';
      url.searchParams.set('retry',retries+1); tile.src=url.toString();
    },700*(retries+1));
  });
  const street = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'});
  L.control.layers({'Satellite':satellite,'Street map':street},{},{position:'bottomleft'}).addTo(map);
  map.attributionControl.addAttribution('ALPR data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors (ODbL)</a>');
  L.control.scale({imperial:true,metric:false,position:'bottomright'}).addTo(map);
  for(const [id,set] of Object.entries(sets)) {
    map.createPane(id).style.zIndex=id === 'deflock' ? 430 : id === 'fl511' ? 420 : id === 'opencctv' ? 410 : 405;
    set.layer=L.layerGroup().addTo(map);
    try {set.enabled=localStorage.getItem('atlas-source-'+id) !== 'off';} catch(_) {}
    $('toggle-'+id).checked=set.enabled;
    $('toggle-'+id).onchange=() => {
      set.enabled=$('toggle-'+id).checked;
      try {localStorage.setItem('atlas-source-'+id,set.enabled ? 'on' : 'off');} catch(_) {}
      if(!set.enabled && selected?.source === id) closePlayer();
      if(set.enabled && (set.status === 'idle' || set.status === 'error')) loadSource(id,catalogVersion);
      else renderCameras();
    };
  }
  origin=L.marker(center,{draggable:true,title:'Your search center — drag to move'}).addTo(map).bindTooltip('Search center');
  radiusCircle=L.circle(center,{radius:20*1609.344,color:'#88caed',weight:1,dashArray:'5 7',fillOpacity:.025}).addTo(map);
  origin.on('dragend',() => {const point=origin.getLatLng(); center=[point.lat,point.lng]; $('location').textContent=`Custom center · ${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}`; loadCameras();});
  $('radius').onchange=() => loadCameras(true);
  $('refresh').onclick=() => loadCameras();
  $('filter').oninput=renderCameras;
  $('retry').onclick=() => selected && selectCamera(selected);
  $('close').onclick=closePlayer;
  video.onplaying=() => {if(selected) $('player-status').textContent=`Playing live · ${sets[selected.source].label} · broadcast delays may apply`;};
  video.onerror=() => {if(selected && !video.hidden) $('player-status').textContent='Unable to play this stream. Reconnect or open the original camera.';};
  $('locate').onclick=() => {
    if(!navigator.geolocation) {$('location').textContent='Geolocation is unavailable. Drag the pin to your location.'; return;}
    navigator.geolocation.getCurrentPosition(position => {
      center=[position.coords.latitude,position.coords.longitude];
      $('location').textContent=`Device location · accuracy about ${Math.round(position.coords.accuracy)} m`;
      loadCameras(true);
    },() => $('location').textContent='Location access unavailable. Your search center is unchanged; drag the pin to move it.',{timeout:12000});
  };
  try {const location=await json('/api/location'); center=[location.lat,location.lon]; $('location').textContent=location.label;}
  catch(_) {$('location').textContent='Cocoa Beach address center · drag the pin to adjust.';}
  await loadCameras(true);
}
init();
