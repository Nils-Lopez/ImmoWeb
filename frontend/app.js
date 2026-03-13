/* ========================================
   FlatSwipe — App Logic
   ======================================== */

// State
let unseen = [];
let currentIndex = 0;
let history = []; // for undo
let currentDetailFlat = null;
let detailPicIndex = 0;
let cardPicIndices = {}; // card id -> pic index

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  setupNav();
  loadConfig();
  loadUnseen();
  refreshStats();
});

// ---- Navigation ----
function setupNav() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      switchView(view);
    });
  });
}

function switchView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

  const view = document.getElementById('view-' + name);
  const nav = document.getElementById('nav-' + name);
  if (view) view.classList.add('active');
  if (nav) nav.classList.add('active');

  if (name === 'liked') loadList('liked');
  if (name === 'masked') loadList('masked');
  if (name === 'settings') refreshStats();
  if (name === 'swipe') renderCards();
}

// Start on swipe
switchView('swipe');

// ---- Config ----
async function loadConfig() {
  const res = await fetch('/api/config');
  const cfg = await res.json();
  document.getElementById('cfg-min-price').value = cfg.min_price || '';
  document.getElementById('cfg-max-price').value = cfg.max_price || '';
  document.getElementById('cfg-postal').value = cfg.postal_codes || '';
  if (cfg.last_scrape) {
    const d = new Date(cfg.last_scrape);
    document.getElementById('last-scrape-info').textContent =
      'Last scrape: ' + d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
  }
}

async function saveConfig() {
  const data = {
    min_price: parseInt(document.getElementById('cfg-min-price').value) || 0,
    max_price: parseInt(document.getElementById('cfg-max-price').value) || 500000,
    postal_codes: document.getElementById('cfg-postal').value.trim(),
  };
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  showToast('Search saved!');
}

// ---- Stats ----
async function refreshStats() {
  const res = await fetch('/api/stats');
  const s = await res.json();
  document.getElementById('stats-display').innerHTML = `
    <div class="stat-card"><div class="num">${s.unseen}</div><div class="label">New</div></div>
    <div class="stat-card"><div class="num" style="color:var(--like)">${s.liked}</div><div class="label">Liked</div></div>
    <div class="stat-card"><div class="num" style="color:var(--nope)">${s.masked}</div><div class="label">Nope</div></div>
  `;
  document.getElementById('badge-liked').textContent = s.liked || '';
  document.getElementById('badge-masked').textContent = s.masked || '';
}

// ---- Scraping ----
async function triggerScrape() {
  const btn = document.getElementById('scrape-btn');
  const progress = document.getElementById('scrape-progress');
  btn.disabled = true;
  btn.textContent = 'Scraping...';
  progress.classList.remove('hidden');

  try {
    const res = await fetch('/api/scrape', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      showToast(err.error || 'Error');
      btn.disabled = false;
      btn.textContent = 'Fetch new listings';
      return;
    }
    pollScrapeStatus(btn, progress);
  } catch (e) {
    showToast('Error starting scrape');
    btn.disabled = false;
    btn.textContent = 'Fetch new listings';
  }
}

function pollScrapeStatus(btn, progress) {
  const interval = setInterval(async () => {
    try {
      const res = await fetch('/api/scrape/status');
      const st = await res.json();
      progress.textContent = st.progress;

      if (!st.running) {
        clearInterval(interval);
        btn.disabled = false;
        btn.textContent = 'Fetch new listings';
        showToast(st.progress);
        loadUnseen();
        refreshStats();
        loadConfig();
      }
    } catch (e) {
      clearInterval(interval);
      btn.disabled = false;
      btn.textContent = 'Fetch new listings';
    }
  }, 2000);
}

// ---- Swipe Cards ----
async function loadUnseen() {
  const res = await fetch('/api/flats/unseen');
  unseen = await res.json();
  currentIndex = 0;
  cardPicIndices = {};
  renderCards();
  refreshStats();
}

function renderCards() {
  const container = document.getElementById('card-container');
  const empty = document.getElementById('empty-state');
  const buttons = document.getElementById('swipe-buttons');

  container.innerHTML = '';

  if (currentIndex >= unseen.length) {
    container.classList.add('hidden');
    buttons.classList.add('hidden');
    empty.classList.remove('hidden');
    return;
  }

  empty.classList.add('hidden');
  container.classList.remove('hidden');
  buttons.classList.remove('hidden');

  // Render top 2 cards (back card + front card)
  const end = Math.min(currentIndex + 2, unseen.length);
  for (let i = end - 1; i >= currentIndex; i--) {
    const card = createCard(unseen[i], i === currentIndex);
    container.appendChild(card);
  }
}

function createCard(flat, isTop) {
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.id = flat.id;

  const pics = flat.pictures || [];
  const picIdx = cardPicIndices[flat.id] || 0;
  const picUrl = pics.length > 0 ? pics[picIdx] : '';

  const dotsHtml = pics.length > 1
    ? `<div class="card-image-dots">${pics.map((_, i) =>
        `<div class="dot${i === picIdx ? ' active' : ''}"></div>`).join('')}</div>`
    : '';

  const tags = [];
  if (flat.bedrooms) tags.push(`${flat.bedrooms} bed`);
  if (flat.bathrooms) tags.push(`${flat.bathrooms} bath`);
  if (flat.surface) tags.push(`${flat.surface} m\u00B2`);
  if (flat.land_surface) tags.push(`${flat.land_surface} m\u00B2 land`);
  if (flat.epc_score) tags.push(`EPC ${flat.epc_score}`);
  if (flat.parking) tags.push(`${flat.parking} parking`);

  card.innerHTML = `
    <div class="card-stamp like">LIKE</div>
    <div class="card-stamp nope">NOPE</div>
    <div class="card-image" style="background-image: url('${picUrl}')">
      ${pics.length > 1 ? `
        <div class="card-image-nav left" data-dir="prev"></div>
        <div class="card-image-nav right" data-dir="next"></div>
      ` : ''}
      <div class="card-image-counter">${pics.length > 0 ? `${picIdx+1}/${pics.length}` : 'No photos'}</div>
      ${dotsHtml}
    </div>
    <div class="card-body" data-action="detail">
      <div>
        <div class="card-price">
          \u20AC ${flat.price ? flat.price.toLocaleString() : '?'}
          ${flat.price_old ? `<span class="card-price-old">\u20AC ${flat.price_old.toLocaleString()}</span>` : ''}
        </div>
        <div class="card-title">${flat.title || flat.subtype || 'Flat'}</div>
        <div class="card-location">${[flat.street, flat.number, flat.postal_code, flat.city].filter(Boolean).join(', ')}</div>
      </div>
      <div>
        <div class="card-tags">${tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>
        <div class="card-tap-detail">Tap for details</div>
      </div>
    </div>
  `;

  if (isTop) {
    setupSwipeGestures(card, flat);
    setupCardImageNav(card, flat);
    card.querySelector('.card-body').addEventListener('click', () => openDetail(flat));
  }

  return card;
}

function setupCardImageNav(card, flat) {
  card.querySelectorAll('.card-image-nav').forEach(nav => {
    nav.addEventListener('click', (e) => {
      e.stopPropagation();
      const pics = flat.pictures || [];
      if (pics.length <= 1) return;
      let idx = cardPicIndices[flat.id] || 0;
      if (nav.dataset.dir === 'next') idx = (idx + 1) % pics.length;
      else idx = (idx - 1 + pics.length) % pics.length;
      cardPicIndices[flat.id] = idx;
      // Update image
      card.querySelector('.card-image').style.backgroundImage = `url('${pics[idx]}')`;
      card.querySelector('.card-image-counter').textContent = `${idx+1}/${pics.length}`;
      card.querySelectorAll('.card-image-dots .dot').forEach((d, i) => {
        d.classList.toggle('active', i === idx);
      });
    });
  });
}

// ---- Swipe Gestures ----
function setupSwipeGestures(card, flat) {
  let startX = 0, startY = 0, currentX = 0, isDragging = false;
  const threshold = 100;

  function onStart(e) {
    // Ignore if clicking image nav
    if (e.target.classList.contains('card-image-nav')) return;
    isDragging = true;
    const point = e.touches ? e.touches[0] : e;
    startX = point.clientX;
    startY = point.clientY;
    currentX = 0;
    card.style.transition = 'none';
  }

  function onMove(e) {
    if (!isDragging) return;
    const point = e.touches ? e.touches[0] : e;
    currentX = point.clientX - startX;
    const rotation = currentX * 0.08;
    card.style.transform = `translateX(${currentX}px) rotate(${rotation}deg)`;

    // Show stamp
    const likeStamp = card.querySelector('.card-stamp.like');
    const nopeStamp = card.querySelector('.card-stamp.nope');
    if (currentX > 30) {
      likeStamp.style.opacity = Math.min((currentX - 30) / 70, 1);
      nopeStamp.style.opacity = 0;
    } else if (currentX < -30) {
      nopeStamp.style.opacity = Math.min((-currentX - 30) / 70, 1);
      likeStamp.style.opacity = 0;
    } else {
      likeStamp.style.opacity = 0;
      nopeStamp.style.opacity = 0;
    }
  }

  function onEnd() {
    if (!isDragging) return;
    isDragging = false;
    card.style.transition = 'transform 0.3s ease-out';

    if (currentX > threshold) {
      animateOut(card, 'right');
      performAction(flat, 'liked');
    } else if (currentX < -threshold) {
      animateOut(card, 'left');
      performAction(flat, 'masked');
    } else {
      card.style.transform = '';
      card.querySelector('.card-stamp.like').style.opacity = 0;
      card.querySelector('.card-stamp.nope').style.opacity = 0;
    }
  }

  card.addEventListener('mousedown', onStart);
  card.addEventListener('mousemove', onMove);
  card.addEventListener('mouseup', onEnd);
  card.addEventListener('mouseleave', onEnd);
  card.addEventListener('touchstart', onStart, { passive: true });
  card.addEventListener('touchmove', onMove, { passive: true });
  card.addEventListener('touchend', onEnd);
}

function animateOut(card, direction) {
  const x = direction === 'right' ? window.innerWidth : -window.innerWidth;
  const rotation = direction === 'right' ? 30 : -30;
  card.style.transition = 'transform 0.4s ease-out';
  card.style.transform = `translateX(${x}px) rotate(${rotation}deg)`;
}

async function performAction(flat, action) {
  history.push({ flat, index: currentIndex });
  currentIndex++;

  await fetch(`/api/flats/${flat.id}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });

  setTimeout(() => renderCards(), 350);
  refreshStats();
}

function swipeAction(action) {
  if (currentIndex >= unseen.length) return;
  const card = document.querySelector('.card');
  if (!card) return;
  const flat = unseen[currentIndex];

  const dir = action === 'liked' ? 'right' : 'left';
  const stamp = card.querySelector(`.card-stamp.${action === 'liked' ? 'like' : 'nope'}`);
  stamp.style.opacity = 1;
  animateOut(card, dir);
  performAction(flat, action);
}

async function undoAction() {
  if (history.length === 0) {
    showToast('Nothing to undo');
    return;
  }
  const last = history.pop();
  await fetch(`/api/flats/${last.flat.id}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'unseen' }),
  });
  currentIndex = last.index;
  renderCards();
  refreshStats();
  showToast('Undone!');
}

// ---- Detail Overlay ----
function openDetail(flat) {
  currentDetailFlat = flat;
  detailPicIndex = 0;
  const overlay = document.getElementById('detail-overlay');
  overlay.classList.remove('hidden');
  renderDetailGallery(flat);
  renderDetailInfo(flat);
  document.body.style.overflow = 'hidden';
}

function closeDetail() {
  document.getElementById('detail-overlay').classList.add('hidden');
  currentDetailFlat = null;
  document.body.style.overflow = '';
}

function renderDetailGallery(flat) {
  const gallery = document.getElementById('detail-gallery');
  const pics = flat.pictures || [];

  if (pics.length === 0) {
    gallery.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#aaa">No photos</div>';
    return;
  }

  const dotsHtml = pics.length > 1
    ? `<div class="detail-gallery-dots">${pics.map((_, i) =>
        `<div class="dot${i === 0 ? ' active' : ''}"></div>`).join('')}</div>`
    : '';

  gallery.innerHTML = `
    <img src="${pics[0]}" alt="Flat photo">
    ${pics.length > 1 ? `
      <div class="detail-gallery-nav left" onclick="detailPic(-1)"></div>
      <div class="detail-gallery-nav right" onclick="detailPic(1)"></div>
    ` : ''}
    <div class="detail-gallery-counter">${1}/${pics.length}</div>
    ${dotsHtml}
  `;
}

function detailPic(dir) {
  if (!currentDetailFlat) return;
  const pics = currentDetailFlat.pictures || [];
  if (pics.length <= 1) return;
  detailPicIndex = (detailPicIndex + dir + pics.length) % pics.length;

  const gallery = document.getElementById('detail-gallery');
  gallery.querySelector('img').src = pics[detailPicIndex];
  gallery.querySelector('.detail-gallery-counter').textContent = `${detailPicIndex+1}/${pics.length}`;
  gallery.querySelectorAll('.detail-gallery-dots .dot').forEach((d, i) => {
    d.classList.toggle('active', i === detailPicIndex);
  });
}

function renderDetailInfo(flat) {
  const info = document.getElementById('detail-info');
  const location = [flat.street, flat.number, flat.postal_code, flat.city].filter(Boolean).join(', ');
  const mapsUrl = `https://www.google.com/maps/place/${encodeURIComponent(location)}`;

  const gridItems = [];
  if (flat.bedrooms != null) gridItems.push({ value: flat.bedrooms, label: 'Bedrooms' });
  if (flat.bathrooms != null) gridItems.push({ value: flat.bathrooms, label: 'Bathrooms' });
  if (flat.surface != null) gridItems.push({ value: `${flat.surface} m\u00B2`, label: 'Living' });
  if (flat.land_surface != null) gridItems.push({ value: `${flat.land_surface} m\u00B2`, label: 'Land' });
  if (flat.parking != null) gridItems.push({ value: flat.parking, label: 'Parking' });
  if (flat.epc_score) gridItems.push({ value: flat.epc_score, label: 'EPC' });
  if (flat.condition) gridItems.push({ value: flat.condition.toLowerCase(), label: 'Condition' });
  if (flat.construction_year) gridItems.push({ value: flat.construction_year, label: 'Built' });

  info.innerHTML = `
    <div class="detail-price">
      \u20AC ${flat.price ? flat.price.toLocaleString() : '?'}
      ${flat.price_old ? `<span class="detail-price-old">\u20AC ${flat.price_old.toLocaleString()}</span>` : ''}
    </div>
    <div class="detail-title">${flat.title || flat.subtype || 'Flat'}</div>
    <div class="detail-location">
      <a href="${mapsUrl}" target="_blank">${location || 'Unknown location'}</a>
    </div>

    <div class="detail-grid">
      ${gridItems.map(item => `
        <div class="detail-grid-item">
          <div class="value">${item.value}</div>
          <div class="label">${item.label}</div>
        </div>
      `).join('')}
    </div>

    ${flat.description ? `
      <div class="detail-description">
        <h3>Description</h3>
        ${flat.description.substring(0, 800)}${flat.description.length > 800 ? '...' : ''}
      </div>
    ` : ''}

    <div class="detail-link">
      <a href="${flat.url}" target="_blank">View on ${flat.provider || 'ImmoWeb'} &rarr;</a>
    </div>
  `;
}

async function detailAction(action) {
  if (!currentDetailFlat) return;
  await fetch(`/api/flats/${currentDetailFlat.id}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });

  // If in swipe view, advance
  if (unseen[currentIndex] && unseen[currentIndex].id === currentDetailFlat.id) {
    history.push({ flat: currentDetailFlat, index: currentIndex });
    currentIndex++;
  }

  closeDetail();
  renderCards();
  refreshStats();
  showToast(action === 'liked' ? 'Liked!' : 'Nope!');
}

// ---- List Views ----
async function loadList(type) {
  const res = await fetch(`/api/flats/${type}`);
  const flats = await res.json();
  const list = document.getElementById(`${type}-list`);

  if (flats.length === 0) {
    list.innerHTML = '<div style="text-align:center;padding:48px;color:var(--text-muted)">No flats here yet</div>';
    return;
  }

  list.innerHTML = flats.map(flat => {
    const pic = flat.pictures && flat.pictures[0] ? flat.pictures[0] : '';
    const meta = [
      flat.bedrooms ? `${flat.bedrooms} bed` : '',
      flat.surface ? `${flat.surface}m\u00B2` : '',
      flat.postal_code || '',
    ].filter(Boolean).join(' \u00B7 ');
    const undoLabel = type === 'liked' ? 'Unlike' : 'Restore';

    return `
      <div class="flat-item" onclick='openDetail(${JSON.stringify(flat).replace(/'/g, "\\'")})'>
        <div class="flat-item-img" style="background-image: url('${pic}')"></div>
        <div class="flat-item-info">
          <div class="flat-item-price">\u20AC ${flat.price ? flat.price.toLocaleString() : '?'}</div>
          <div class="flat-item-title">${flat.title || flat.subtype || 'Flat'}</div>
          <div class="flat-item-meta">${meta}</div>
        </div>
        <div class="flat-item-action">
          <button onclick="event.stopPropagation(); restoreFlat(${flat.id})">${undoLabel}</button>
        </div>
      </div>
    `;
  }).join('');
}

async function restoreFlat(id) {
  await fetch(`/api/flats/${id}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'unseen' }),
  });
  // Reload current view
  const activeView = document.querySelector('.view.active');
  if (activeView.id === 'view-liked') loadList('liked');
  if (activeView.id === 'view-masked') loadList('masked');
  // Refresh unseen
  const res = await fetch('/api/flats/unseen');
  unseen = await res.json();
  currentIndex = 0;
  refreshStats();
  showToast('Restored!');
}

// ---- Seed Data ----
async function seedData() {
  const res = await fetch('/api/seed', { method: 'POST' });
  const data = await res.json();
  showToast(`Loaded ${data.count} demo flats!`);
  loadUnseen();
  refreshStats();
}

// ---- Toast ----
function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.remove('hidden');
  // Reset animation
  toast.style.animation = 'none';
  toast.offsetHeight; // trigger reflow
  toast.style.animation = '';
  setTimeout(() => toast.classList.add('hidden'), 2200);
}
