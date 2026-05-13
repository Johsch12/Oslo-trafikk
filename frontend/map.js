// ─── KART ────────────────────────────────────────────────────
const canvasRenderer = L.canvas({ padding: 0.5, tolerance: 5 });

const map = L.map('map', { center: [59.913, 10.752], zoom: 13, zoomControl: false });

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap © CARTO',
  maxZoom: 19,
}).addTo(map);

// ─── KONSTANTER ──────────────────────────────────────────────
const COLORS      = ['#00ff88', '#8eff5a', '#ffd600', '#ff4d00', '#7b00ff'];
const ROAD_W      = { motorway: 7, trunk: 7, primary: 5, secondary: 4, tertiary: 3 };
const CONGESTION  = ['Fri flyt', 'Lav kø', 'Moderat kø', 'Mye kø', 'Stillestående'];

// ─── STATE ───────────────────────────────────────────────────
const roadGroup   = L.layerGroup().addTo(map);
let roadItems     = [];       // [{layer, way, baseWeight}] — beholdes ved toggle
let renderedData  = null;
let roadData      = null;
let fetchedBounds = null;
let weatherData   = null;
let holidayData   = {};       // {dateStr: {type, factor, label, emoji}}
let currentOffset = 0;        // timer (kan være 0.5, 1.0, 1.5 …)
let trafficOn     = true;
let routeLayer    = null;
let routeMarkers  = [];
let roadsCtrl     = null;
let loadTimer     = null;
let rafId         = null;
let sugTimer      = null;

// ─── LOADING BAR ─────────────────────────────────────────────
const loadingBar = document.getElementById('loadingBar');
function setLoading(on) { loadingBar?.classList.toggle('active', on); }

// ─── HELLIGDAG-HJELPER ───────────────────────────────────────
function dateKey(msOffset) {
  const d = new Date(Date.now() + msOffset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function getDayInfo(hourOffset) {
  return holidayData[dateKey(hourOffset * 3600000)] || { type: 'weekday', factor: 1.0, label: null, emoji: null };
}

async function loadHolidays() {
  try {
    const r = await fetch('/api/holidays');
    holidayData = await r.json();
    // Re-render hvis veier allerede er lastet
    if (roadData && trafficOn) renderRoads(roadData, currentOffset);
    updateHolidayBadge(currentOffset);
  } catch (e) {}
}

function updateHolidayBadge(offset) {
  const info = getDayInfo(offset);
  const badge = document.getElementById('holidayBadge');
  if (!badge) return;
  if (info.label) {
    badge.textContent = (info.emoji ? info.emoji + ' ' : '') + info.label;
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
  }
}

// ─── PREDIKSJON ──────────────────────────────────────────────
function predictScore(way, hourOffset) {
  const target = new Date(Date.now() + hourOffset * 3600000);
  const h      = target.getHours();
  const hw     = way.tags?.highway || '';
  const dinfo  = getDayInfo(hourOffset);

  const isNight  = h >= 23 || h <= 5;
  const isOff    = ['holiday', 'bridge', 'holiday_period', 'summer'].includes(dinfo.type);
  const isWeekend = dinfo.type === 'weekend' || isOff;
  const isRushM  = h >= 7  && h <= 9  && !isWeekend;
  const isRushE  = h >= 15 && h <= 18 && !isWeekend;

  let score = 1;
  if (isNight)            score = 0;
  else if (isOff)         score = 0;
  else if (isWeekend)     score = 1;
  else if (isRushM || isRushE) {
    score = (hw === 'motorway' || hw === 'trunk') ? 3 : hw === 'primary' ? 2 : 1;
  }

  // Litt variasjon per vei-ID
  if (way.id) score = Math.max(0, Math.min(4, score + (way.id % 3) - 1));

  // Vær-effekter
  if (weatherData?.precipitation > 1)  score = Math.min(4, score + 1);
  if (weatherData?.temperature   < 0)  score = Math.min(4, score + 1);

  // Helligdag-faktor (0.1 = helligdag, 0.55 = helg, 1.0 = vanlig hverdag …)
  score = Math.max(0, Math.min(4, Math.round(score * dinfo.factor)));
  return score;
}

// ─── TEGN VEIER ──────────────────────────────────────────────
function renderRoads(data, offset) {
  if (!data?.elements?.length) return;

  if (data === renderedData && roadItems.length) {
    // Kun restyle farger — mye raskere enn fjerne/gjenskape
    roadItems.forEach(({ layer, way }) =>
      layer.setStyle({ color: COLORS[predictScore(way, offset)] })
    );
    return;
  }

  // Nytt datasett — rebuild
  roadGroup.clearLayers();
  roadItems = [];
  renderedData = data;

  const zoom = map.getZoom();
  data.elements.forEach(way => {
    if (!way.geometry) return;
    const hw = way.tags?.highway || '';
    if (zoom < 13 && hw === 'tertiary') return;
    if (zoom < 12 && (hw === 'secondary' || hw === 'tertiary')) return;

    const coords     = way.geometry.map(p => [p.lat, p.lon]);
    const score      = predictScore(way, offset);
    const baseWeight = ROAD_W[hw] || 3;
    const name       = way.tags?.name || way.tags?.ref || hw;

    const layer = L.polyline(coords, {
      color: COLORS[score], weight: baseWeight, opacity: 0.85, renderer: canvasRenderer,
    }).addTo(roadGroup);

    layer.on('mouseover', function(e) {
      const s = predictScore(way, currentOffset);
      this.setStyle({ weight: baseWeight + 3, opacity: 1 });
      L.popup({ closeButton: false, offset: [0, -4] })
        .setLatLng(e.latlng)
        .setContent(`<div style="font-family:'Space Mono',monospace;font-size:11px;background:#12121a;color:#e8e8f0;padding:8px 12px;border-radius:6px;border:1px solid #1e1e2e;white-space:nowrap">
          <strong>${name}</strong><br>
          <span style="color:${COLORS[s]}">● ${CONGESTION[s]}</span>
        </div>`)
        .openOn(map);
    });
    layer.on('mouseout', function() {
      this.setStyle({ weight: baseWeight, opacity: 0.85 });
      map.closePopup();
    });

    roadItems.push({ layer, way, baseWeight });
  });
}

// ─── LAST VEIER ──────────────────────────────────────────────
function boundsOverlap(fetched, current) {
  if (!fetched || !current) return 0;
  const latO = Math.max(0, Math.min(fetched.getNorth(), current.getNorth()) - Math.max(fetched.getSouth(), current.getSouth()));
  const lonO = Math.max(0, Math.min(fetched.getEast(),  current.getEast())  - Math.max(fetched.getWest(),  current.getWest()));
  const areaC = (current.getNorth() - current.getSouth()) * (current.getEast() - current.getWest());
  return areaC > 0 ? (latO * lonO) / areaC : 0;
}

async function loadRoads() {
  const zoom = map.getZoom();
  if (zoom < 12) {
    roadGroup.clearLayers(); roadItems = []; renderedData = null; fetchedBounds = null;
    return;
  }

  const b = map.getBounds();
  if (boundsOverlap(fetchedBounds, b) > 0.8 && roadData) {
    if (roadData !== renderedData) renderRoads(roadData, currentOffset);
    return;
  }

  if (roadsCtrl) roadsCtrl.abort();
  roadsCtrl = new AbortController();
  const padded = b.pad(0.3);
  fetchedBounds = padded;

  setLoading(true);
  try {
    const s = padded.getSouth().toFixed(4), w = padded.getWest().toFixed(4);
    const n = padded.getNorth().toFixed(4), e = padded.getEast().toFixed(4);
    const res = await fetch(`/api/roads?south=${s}&west=${w}&north=${n}&east=${e}`,
      { signal: roadsCtrl.signal });
    const data = await res.json();
    roadData = data;
    renderRoads(data, currentOffset);
  } catch (err) {
    if (err.name !== 'AbortError') { console.warn('Vei-feil:', err); fetchedBounds = null; }
  } finally {
    setLoading(false);
  }
}

map.on('moveend zoomend', () => { clearTimeout(loadTimer); loadTimer = setTimeout(loadRoads, 800); });

// ─── KØ AV/PÅ ────────────────────────────────────────────────
function toggleTrafficLayer() {
  trafficOn = !trafficOn;
  const btn = document.getElementById('toggleBtn');
  if (trafficOn) {
    map.addLayer(roadGroup);
    // Restyle med gjeldende offset (slider kan ha beveget seg mens trafikk var av)
    if (roadData) { renderedData = null; renderRoads(roadData, currentOffset); }
    btn.textContent = 'Kø AV';
    btn.style.cssText += ';border-color:var(--accent);color:var(--accent)';
  } else {
    map.removeLayer(roadGroup);
    btn.textContent = 'Kø PÅ';
    btn.style.borderColor = '';
    btn.style.color = '';
  }
}

// ─── AUTOCOMPLETE ────────────────────────────────────────────
async function fetchSuggestions(query, id) {
  clearTimeout(sugTimer);
  if (query.length < 2) { hideSuggestions(id); return; }
  sugTimer = setTimeout(async () => {
    try {
      const res  = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      const oslo = data.filter(r => JSON.stringify(r.address || {}).toLowerCase().includes('oslo'));
      showSuggestions(oslo.length ? oslo : data.slice(0, 5), id);
    } catch (e) {}
  }, 400);
}

function formatSuggestion(r) {
  const a = r.address || {};
  const parts = [];
  if (a.road) parts.push(a.road + (a.house_number ? ' ' + a.house_number : ''));
  if (a.suburb || a.neighbourhood) parts.push(a.suburb || a.neighbourhood);
  if (a.city || a.municipality)    parts.push(a.city || a.municipality);
  return parts.length ? parts.join(', ') : r.display_name.split(',').slice(0, 2).join(',');
}

function showSuggestions(results, id) {
  const wrapper = document.getElementById(id).closest('.search-wrapper');
  let list = document.getElementById(id + 'List');
  if (!list) {
    list = document.createElement('div');
    list.id = id + 'List';
    list.className = 'suggestions';
    wrapper.appendChild(list);
  }
  list._results = results;
  list.innerHTML = results.map((r, i) => `
    <div class="suggestion-item" onmousedown="selectSuggestion('${id}',${i})">
      <span class="sug-icon">${r.class === 'highway' ? '🛣' : '📍'}</span>
      <span class="sug-main">${formatSuggestion(r)}</span>
    </div>`).join('');
  list.style.display = results.length ? 'block' : 'none';
}

function hideSuggestions(id) {
  const el = document.getElementById(id + 'List');
  if (el) el.style.display = 'none';
}

function selectSuggestion(id, idx) {
  const list  = document.getElementById(id + 'List');
  if (!list?._results) return;
  const r     = list._results[idx];
  const input = document.getElementById(id);
  input.value       = formatSuggestion(r);
  input.dataset.lat = r.lat;
  input.dataset.lon = r.lon;
  hideSuggestions(id);
  map.flyTo([parseFloat(r.lat), parseFloat(r.lon)], 15, { duration: 0.8 });
  const f = document.getElementById('fromInput');
  const t = document.getElementById('toInput');
  if (f.dataset.lat && t.dataset.lat) drawRoute();
}

// ─── SØK ─────────────────────────────────────────────────────
async function searchRoute() {
  const f = document.getElementById('fromInput');
  const t = document.getElementById('toInput');
  if (f.value && !f.dataset.lat) await geocodeInput('fromInput');
  if (t.value && !t.dataset.lat) await geocodeInput('toInput');
  if (f.dataset.lat && t.dataset.lat) {
    drawRoute();
  } else if (f.dataset.lat) {
    map.flyTo([parseFloat(f.dataset.lat), parseFloat(f.dataset.lon)], 15, { duration: 0.8 });
  }
}

async function geocodeInput(id) {
  const input = document.getElementById(id);
  try {
    const res  = await fetch(`/api/geocode?q=${encodeURIComponent(input.value + ' Oslo')}`);
    const data = await res.json();
    if (!data.length) return;
    let list = document.getElementById(id + 'List');
    if (!list) {
      list = document.createElement('div');
      list.id = id + 'List';
      input.closest('.search-wrapper').appendChild(list);
    }
    list._results = data;
    selectSuggestion(id, 0);
  } catch (e) {}
}

// ─── RUTE ─────────────────────────────────────────────────────
async function drawRoute() {
  const f = document.getElementById('fromInput');
  const t = document.getElementById('toInput');
  if (!f.dataset.lat || !t.dataset.lat) return;
  clearRoute();

  try {
    const res  = await fetch(
      `/api/route?from_lon=${f.dataset.lon}&from_lat=${f.dataset.lat}&to_lon=${t.dataset.lon}&to_lat=${t.dataset.lat}`
    );
    const data = await res.json();
    if (!data.routes?.length) return;

    const coords     = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
    const durMin     = Math.round(data.routes[0].duration / 60);
    const distKm     = (data.routes[0].distance / 1000).toFixed(1);
    const h          = (new Date().getHours() + currentOffset) % 24;
    const dinfo      = getDayInfo(currentOffset);
    const isOff      = ['holiday', 'bridge', 'holiday_period'].includes(dinfo.type);
    const isRush     = !isOff && ((h >= 7 && h <= 9) || (h >= 15 && h <= 18));
    const mult       = isRush ? 1.6 : (isOff ? 0.7 : 1.0);
    const adjMin     = Math.round(durMin * mult);

    routeLayer = L.polyline(coords, {
      color: COLORS[isRush ? 3 : (isOff ? 0 : 1)], weight: 7, opacity: 0.95,
    }).addTo(map);
    map.fitBounds(routeLayer.getBounds(), { padding: [60, 60] });

    const pin = c => `<div style="width:14px;height:14px;background:${c};border-radius:50%;border:3px solid #0a0a0f;box-shadow:0 0 8px ${c}"></div>`;
    routeMarkers.push(
      L.marker([f.dataset.lat, f.dataset.lon], { icon: L.divIcon({ className: '', html: pin('#00ff88') }) }).addTo(map),
      L.marker([t.dataset.lat, t.dataset.lon], { icon: L.divIcon({ className: '', html: pin('#ff4d00') }) }).addTo(map),
    );

    document.getElementById('travelTime').textContent = adjMin + ' min';
    const suffix = isRush ? 'Rushtid 🔴' : isOff ? (dinfo.label || 'Lav trafikk 🟢') : 'Normal 🟢';
    document.getElementById('travelSub').textContent = `Bil · ${distKm} km · ${suffix}`;
    const btn = document.getElementById('clearRouteBtn');
    if (btn) btn.style.display = 'flex';
  } catch (e) { console.warn('Rute-feil:', e); }
}

function clearRoute() {
  if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
  routeMarkers.forEach(m => map.removeLayer(m));
  routeMarkers = [];
  document.getElementById('travelTime').textContent = '-- min';
  document.getElementById('travelSub').textContent  = 'Velg rute for estimat';
  const btn = document.getElementById('clearRouteBtn');
  if (btn) btn.style.display = 'none';
}

// ─── GEOLOKASJON ─────────────────────────────────────────────
async function geolocate(id) {
  if (!navigator.geolocation) return;
  const input = document.getElementById(id);
  const orig  = input.placeholder;
  input.placeholder = 'Finner posisjon...';
  navigator.geolocation.getCurrentPosition(async pos => {
    const { latitude: lat, longitude: lon } = pos.coords;
    input.dataset.lat = lat;
    input.dataset.lon = lon;
    try {
      const r    = await fetch(`/api/reverse-geocode?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}`);
      const data = await r.json();
      input.value = data.display_name?.split(',').slice(0, 2).join(', ') || 'Min posisjon';
    } catch { input.value = 'Min posisjon'; }
    input.placeholder = orig;
    map.flyTo([lat, lon], 14, { duration: 0.8 });
    const f = document.getElementById('fromInput');
    const t = document.getElementById('toInput');
    if (f.dataset.lat && t.dataset.lat) drawRoute();
  }, () => { input.placeholder = orig; });
}

// ─── SLIDER (requestAnimationFrame) ──────────────────────────
const slider      = document.getElementById('timeSlider');
const timeDisplay = document.getElementById('timeDisplay');

function applySliderValue(val) {
  const offset    = val * 0.5;
  currentOffset   = offset;

  // Oppdater display
  if (val === 0) {
    timeDisplay.textContent = 'NÅ';
  } else {
    const t   = new Date(Date.now() + val * 1800000);
    const hh  = String(t.getHours()).padStart(2, '0');
    const mm  = String(t.getMinutes()).padStart(2, '0');
    const tot = val * 30;
    const lh  = Math.floor(tot / 60);
    const lm  = tot % 60;
    const lbl = lh === 0 ? `+${lm}min` : lm === 0 ? `+${lh}t` : `+${lh}t ${lm}min`;
    timeDisplay.textContent = `${lbl} (${hh}:${mm})`;
  }

  // Helligdag-badge
  updateHolidayBadge(offset);

  // Fargeoppdate veier (restyle, ikke rebuild)
  if (roadData && trafficOn) renderRoads(roadData, offset);

  // Rutefarge og reisetidstekst
  if (routeLayer) {
    const h      = (new Date().getHours() + offset) % 24;
    const dinfo  = getDayInfo(offset);
    const isOff  = ['holiday', 'bridge', 'holiday_period'].includes(dinfo.type);
    const isRush = !isOff && ((h >= 7 && h <= 9) || (h >= 15 && h <= 18));
    routeLayer.setStyle({ color: COLORS[isRush ? 3 : (isOff ? 0 : 1)] });
    const sub   = document.getElementById('travelSub');
    const match = sub?.textContent.match(/Bil · ([\d.]+) km/);
    if (match) {
      const suffix = isRush ? 'Rushtid 🔴' : isOff ? (dinfo.label || 'Lav trafikk 🟢') : 'Normal 🟢';
      sub.textContent = `Bil · ${match[1]} km · ${suffix}`;
    }
  }
}

slider.addEventListener('input', () => {
  const val = parseInt(slider.value);
  if (rafId) cancelAnimationFrame(rafId);
  rafId = requestAnimationFrame(() => { applySliderValue(val); rafId = null; });
});

// ─── MODAL ────────────────────────────────────────────────────
function openModal()  { document.getElementById('modal').classList.add('open'); }
function closeModal() { document.getElementById('modal').classList.remove('open'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

['mTime', 'mReturn', 'mWeather'].forEach(id =>
  document.getElementById(id).addEventListener('input', updateModal)
);

function updateModal() {
  const h  = parseInt(document.getElementById('mTime').value);
  const ret = parseInt(document.getElementById('mReturn').value);
  const w  = parseInt(document.getElementById('mWeather').value);
  document.getElementById('mTimeVal').textContent   = String(h).padStart(2,'0') + ':00';
  document.getElementById('mReturnVal').textContent = ret ? 'Ja' : 'Nei';
  document.getElementById('mWeatherVal').textContent = ['Ignorerer', 'Middels', 'Viktig'][w];

  const isRush   = (h >= 7 && h <= 9) || (h >= 15 && h <= 18);
  const carMins  = isRush ? 35 + w * 5 : 15;
  const busMins  = 22;
  const busWins  = busMins < carMins;

  document.getElementById('opt1').className         = 'modal-option' + (busWins ? ' winner' : '');
  document.getElementById('opt1Icon').textContent   = busWins ? '🚇' : '🚗';
  document.getElementById('opt1Icon').className     = 'option-icon ' + (busWins ? 'bus' : 'car');
  document.getElementById('opt1Label').textContent  = busWins ? 'Ta kollektivt' : 'Kjør bil';
  document.getElementById('opt1Detail').textContent = busWins
    ? `T-bane · ${busMins} min · Slipper kø`
    : `Ring 1 · ${carMins} min · Lite kø`;

  document.getElementById('opt2').className         = 'modal-option' + (!busWins ? ' winner' : '');
  document.getElementById('opt2Icon').textContent   = busWins ? '🚗' : '🚇';
  document.getElementById('opt2Icon').className     = 'option-icon ' + (busWins ? 'car' : 'bus');
  document.getElementById('opt2Label').textContent  = busWins ? 'Kjør bil' : 'Ta kollektivt';
  document.getElementById('opt2Detail').textContent = busWins
    ? `Ring 1 · ${carMins} min · ${isRush ? 'Mye kø' : 'Normal'}`
    : `T-bane · ${busMins} min`;
}

function swapAddresses() {
  const f = document.getElementById('fromInput');
  const t = document.getElementById('toInput');
  [f.value, t.value]             = [t.value, f.value];
  [f.dataset.lat, t.dataset.lat] = [t.dataset.lat, f.dataset.lat];
  [f.dataset.lon, t.dataset.lon] = [t.dataset.lon, f.dataset.lon];
  if (f.dataset.lat && t.dataset.lat) drawRoute();
}

// ─── VÆR ─────────────────────────────────────────────────────
async function loadWeather() {
  try {
    const r    = await fetch('/api/weather');
    const data = await r.json();
    const ts   = data.properties?.timeseries?.[0];
    if (!ts) return;
    const d      = ts.data.instant.details;
    const precip = ts.data.next_1_hours?.details?.precipitation_amount || 0;
    weatherData  = { temperature: d.air_temperature, precipitation: precip, wind_speed: d.wind_speed };
    document.getElementById('weatherTemp').textContent = Math.round(d.air_temperature) + '°C';
    const icon = precip > 2 ? '🌧' : precip > 0.1 ? '🌦' : d.air_temperature < 0 ? '❄️' : d.air_temperature > 20 ? '☀️' : '🌤';
    document.getElementById('weatherDesc').textContent = icon + ' ' + Math.round(d.wind_speed) + ' m/s';
    // Restyle veier med oppdatert vær
    if (roadData && trafficOn) renderRoads(roadData, currentOffset);
  } catch (e) {
    document.getElementById('weatherDesc').textContent = '–';
  }
}

// ─── OPPSTART ────────────────────────────────────────────────
loadHolidays();
loadWeather();
loadRoads();
setInterval(loadWeather, 300000);   // vær hvert 5. min
setInterval(loadHolidays, 3600000); // helligdager hvert 60. min (dekker midnatt-overgang)
