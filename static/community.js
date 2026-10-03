'use strict';
(() => {
  const el = id => document.getElementById(id);
  const storageKey = 'atlas-community-posts-v1';
  let posts = [], active = null;
  function embedUrl(value) {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== 'www.snapchat.com' || url.port ||
        url.username || url.password || !/^\/(?:[A-Za-z0-9_@.-]+\/)+embed\/?$/.test(url.pathname)) {
      throw new Error('Use Snapchat’s copied embed code or an https://www.snapchat.com/…/embed URL.');
    }
    url.hash = '';
    return url.href;
  }
  function parse(value) {
    value = value.trim();
    if (value.startsWith('<')) {
      const doc = new DOMParser().parseFromString(value, 'text/html');
      const block = doc.querySelector('[data-snapchat-embed-url]');
      if (!block) throw new Error('No Snapchat embed found. Use Share → Embed → Copy code.');
      return embedUrl(block.getAttribute('data-snapchat-embed-url'));
    }
    return embedUrl(value);
  }
  function status(message) { el('community-status').textContent = message; }
  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify(posts)); }
    catch (_) { status('Browser storage is unavailable. These links will last only for this session.'); }
  }
  function stop() {
    active = null;
    el('community-frame').removeAttribute('src');
    el('community-view').hidden = true;
  }
  function show(post) {
    active = post.url;
    el('community-view-title').textContent = post.title;
    el('community-original').href = post.url.replace(/\/embed\/?(?=\?|$)/, '');
    el('community-view').hidden = false;
    el('community-frame').src = post.url;
    status('Public post selected. Playback and availability are controlled by Snapchat.');
  }
  function render() {
    el('community-list').replaceChildren();
    if (!posts.length) {
      const p = document.createElement('p');
      p.textContent = 'No saved posts yet. Add an embed above to view it beside the map.';
      el('community-list').append(p);
    }
    for (const post of posts) {
      const row = document.createElement('div'); row.className = 'community-row';
      const open = document.createElement('button'); open.textContent = post.title;
      open.onclick = () => show(post);
      const remove = document.createElement('button'); remove.className = 'secondary';
      remove.textContent = 'Remove'; remove.setAttribute('aria-label', 'Remove '+post.title);
      remove.onclick = () => {
        if (active === post.url) stop();
        posts = posts.filter(item => item.url !== post.url); save(); render();
      };
      row.append(open, remove); el('community-list').append(row);
    }
  }
  function toggle(open) {
    el('community-panel').hidden = !open;
    el('community-toggle').setAttribute('aria-expanded', String(open));
    if (!open) stop();
    try { localStorage.setItem('atlas-community-open', open ? 'on' : 'off'); } catch (_) {}
    if (typeof map !== 'undefined' && map) requestAnimationFrame(() => map.invalidateSize());
  }
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (Array.isArray(stored)) posts = stored.slice(0, 50).flatMap(post => {
      try { return [{url:embedUrl(post.url), title:String(post.title || 'Snapchat post').slice(0,100)}]; }
      catch (_) { return []; }
    });
  } catch (_) {}
  el('community-form').onsubmit = event => {
    event.preventDefault();
    try {
      const url = parse(el('community-code').value);
      const existing = posts.find(post => post.url === url);
      if (!existing && posts.length >= 50) throw new Error('Remove a saved post before adding more (50 maximum).');
      const post = existing || {url, title:el('community-title').value.trim() || 'Snapchat public post'};
      if (!existing) posts.push(post);
      status(''); save(); render(); show(post); el('community-form').reset();
    } catch (error) { status(error.message); }
  };
  el('community-toggle').onclick = () => toggle(el('community-panel').hidden);
  el('community-close').onclick = () => { toggle(false); el('community-toggle').focus(); };
  el('community-stop').onclick = stop;
  render();
  try { toggle(localStorage.getItem('atlas-community-open') === 'on'); } catch (_) {}
})();
