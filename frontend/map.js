// ─── RENDERER & MAP ──────────────────────────────────────────
const canvasRenderer = L.canvas({ padding: 0.5, tolerance: 5 });

const map = L.map('map', {
  center: [59.913, 10.752],
  zoom: 13,
  zoomControl: false
});

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap © CARTO',
  maxZoom: 19
}).addTo(map);

// ─── KONSTANTER ──────────────────────────────────────────────
const COLORS = ['#00ff88', '#8eff5a', '#ffd600', '#ff4d00', '#7b00ff'];
const ROAD_WEIGHT = { motorway: 7, trunk: 7, primary: 5, secondary: 4, tertiary: 3 };
const ROAD_LABEL = ['Fri flyt', 'Lav kø', 'Moderat kø', 'Mye kø', 'Stillestående'];

// ─── STATE ───────────────────────────────────────────────────
let roadItems = [];       // [{layer, way, baseWeight}]
let renderedData = null;  // referanse til sist rendret datasett
let roadData = null;      // sist hentede veidata
let fetchedBounds = null; // padded bounds fra siste vellykkede henting
let weatherData = null;
let currentHourOffset = 0;
let trafficLayerOn = true;
let routeLayer = null;
let routeMarkers = [];
let suggestionTimeout = null;
let loadTimeout = null;
let roadsController = null;

// ─── LASTINGSLINJE ───────────────────────────────────────────
function setLoading(on) {
  document.getElementById('loadingBar')?.classList.toggle('active', on);
}

// ─── PREDIKER KØ ─────────────────────────────────────────────
function predictScore(way, hourOffset) {
  const now = new Date();
  const h = (now.getHours() + hourOffset) % 24;
  const isWeekend = [0, 6].includes(now.getDay());
  const isRushM = h >= 7 && h <= 9;
  const isRushE = h >= 15 && h <= 18;
  const isNight = h >= 23 || h <= 5;
  const hw = way.tags?.highway || '';
  let score = 1;
  if (isNight) score = 0;
  else if (isWeekend) score = 1;
  else if (isRushM || isRushE) {
    score = hw === 'motorway' || hw === 'trunk' ? 3 : hw === 'primary' ? 2 : 1;
  }
  if (way.id) score = Math.max(0, Math.min(4, score + (way.id % 3) - 1));
  if (weatherData?.precipitation > 1) score = Math.min(4, score + 1);
  if (weatherData?.temperature < 0) score = Math.min(4, score + 1);
  return Math.round(score);
}

// ─── TEGN VEIER ──────────────────────────────────────────────
function renderRoads(data, hourOffset) {
  if (!trafficLayerOn || !data?.elements?.length) {
    roadItems.forEach(({ layer }) => map.removeLayer(layer));
    roadItems = [];
    renderedData = null;
    return;
  }

  // Samme datasett → bare oppdater farger (mye raskere enn fjerne/gjenskape)
  if (data === renderedData && roadItems.length) {
    roadItems.forEach(({ layer, way }) => {
      layer.setStyle({ color: COLORS[predictScore(way, hourOffset)] });
    });
    return;
  }

  // Nytt datasett → fjern gamle lag og bygg nye
  roadItems.forEach(({ layer }) => map.removeLayer(layer));
  roadItems = [];
  renderedData = data;

  const zoom = map.getZoom();

  data.elements.forEach(way => {
    if (!way.geometry) return;
    const hw = way.tags?.highway || '';
    if (zoom < 13 && hw === 'tertiary') return;
    if (zoom < 12 && (hw === 'secondary' || hw === 'tertiary')) return;

    const coords = way.geometry.map(p => [p.lat, p.lon]);
    const score = predictScore(way, hourOffset);
    const baseWeight = ROAD_WEIGHT[hw] || 3;
    const name = way.tags?.name || way.tags?.ref || hw;

    const layer = L.polyline(coords, {
      color: COLORS[score],
      weight: baseWeight,
      opacity: 0.85,
      renderer: canvasRenderer
    }).addTo(map);

    layer.on('mouseover', function(e) {
      const s = predictScore(way, currentHourOffset);
      this.setStyle({ weight: baseWeight + 3, opacity: 1 });
      L.popup({ closeButton: false, offset: [0, -4] })
        .setLatLng(e.latlng)
        .setContent(`<div style="font-family:'Space Mono',monospace;font-size:11px;background:#12121a;color:#e8e8f0;padding:8px 12px;border-radius:6px;border:1px solid #1e1e2e;white-space:nowrap">
          <strong>${name}</strong><br>
          <span style="color:${COLORS[s]}">● ${ROAD_LABEL[s]}</span>
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
async function loadRoads() {
  const zoom = map.getZoom();
  if (zoom < 12) {
    roadItems.forEach(({ layer }) => map.removeLayer(layer));
    roadItems = [];
    renderedData = null;
    fetchedBounds = null;
    return;
  }

  const b = map.getBounds();

  // Allerede data som dekker dette området → gjenbruk
  if (fetchedBounds?.contains(b) && roadData) {
    if (roadData !== renderedData) renderRoads(roadData, currentHourOffset);
    return;
  }

  if (roadsController) roadsController.abort();
  roadsController = new AbortController();

  // Hent med 25% marg → småpanning krever ikke ny henting
  const padded = b.pad(0.25);
  fetchedBounds = padded;

  setLoading(true);
  try {
    const s = padded.getSouth().toFixed(4);
    const w = padded.getWest().toFixed(4);
    const n = padded.getNorth().toFixed(4);
    const e = padded.getEast().toFixed(4);
    const res = await fetch(`/api/roads?south=${s}&west=${w}&north=${n}&east=${e}`,
      { signal: roadsController.signal });
    const data = await res.json();
    roadData = data;
    renderRoads(data, currentHourOffset);
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.log('Vei-feil:', e);
      fetchedBounds = null;
    }
  } finally {
    setLoading(false);
  }
}

map.on('moveend zoomend', () => {
  clearTimeout(loadTimeout);
  loadTimeout = setTimeout(loadRoads, 500);
});

// ─── TRAFIKK AV/PÅ ───────────────────────────────────────────
function toggleTrafficLayer() {
  trafficLayerOn = !trafficLayerOn;
  const btn = document.getElementById('toggleBtn');
  if (trafficLayerOn) {
    btn.textContent = 'Kø AV';
    btn.style.borderColor = 'var(--accent)';
    btn.style.color = 'var(--accent)';
    if (roadData) renderRoads(roadData, currentHourOffset);
  } else {
    btn.textContent = 'Kø PÅ';
    btn.style.borderColor = '';
    btn.style.color = '';
    roadItems.forEach(({ layer }) => map.removeLayer(layer));
    roadItems = [];
    renderedData = null;
  }
}

// ─── AUTOCOMPLETE ────────────────────────────────────────────
async function fetchSuggestions(query, inputId) {
  clearTimeout(suggestionTimeout);
  if (query.length < 2) { hideSuggestions(inputId); return; }
  suggestionTimeout = setTimeout(async () => {
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      const oslo = data.filter(r => JSON.stringify(r.address || {}).toLowerCase().includes('oslo'));
      showSuggestions(oslo.length ? oslo : data.slice(0, 5), inputId);
    } catch (e) {}
  }, 350);
}

function formatSuggestion(r) {
  const addr = r.address || {};
  const parts = [];
  if (addr.road) parts.push(addr.road + (addr.house_number ? ' ' + addr.house_number : ''));
  if (addr.suburb || addr.neighbourhood) parts.push(addr.suburb || addr.neighbourhood);
  if (addr.city || addr.municipality) parts.push(addr.city || addr.municipality);
  return parts.length ? parts.join(', ') : r.display_name.split(',').slice(0, 2).join(',');
}

function showSuggestions(results, inputId) {
  const wrapper = document.getElementById(inputId).closest('.search-wrapper');
  let list = document.getElementById(inputId + 'List');
  if (!list) {
    list = document.createElement('div');
    list.id = inputId + 'List';
    list.className = 'suggestions';
    wrapper.appendChild(list);
  }
  if (!results.length) { list.style.display = 'none'; return; }
  list._results = results;
  list.innerHTML = results.map((r, i) => `
    <div class="suggestion-item" onmousedown="selectSuggestion('${inputId}', ${i})">
      <span class="sug-icon">${r.class === 'highway' ? '🛣' : '📍'}</span>
      <span class="sug-main">${formatSuggestion(r)}</span>
    </div>
  `).join('');
  list.style.display = 'block';
}

function hideSuggestions(inputId) {
  const list = document.getElementById(inputId + 'List');
  if (list) list.style.display = 'none';
}

function selectSuggestion(inputId, index) {
  const list = document.getElementById(inputId + 'List');
  if (!list?._results) return;
  const r = list._results[index];
  const input = document.getElementById(inputId);
  input.value = formatSuggestion(r);
  input.dataset.lat = r.lat;
  input.dataset.lon = r.lon;
  hideSuggestions(inputId);
  map.setView([parseFloat(r.lat), parseFloat(r.lon)], 15);
  const from = document.getElementById('fromInput');
  const to = document.getElementById('toInput');
  if (from.dataset.lat && to.dataset.lat) drawRoute();
}

// ─── SØK ─────────────────────────────────────────────────────
async function searchRoute() {
  const from = document.getElementById('fromInput');
  const to = document.getElementById('toInput');
  if (from.value && !from.dataset.lat) await geocodeInput('fromInput');
  if (to.value && !to.dataset.lat) await geocodeInput('toInput');
  if (from.dataset.lat && to.dataset.lat) {
    drawRoute();
  } else if (from.dataset.lat) {
    map.setView([parseFloat(from.dataset.lat), parseFloat(from.dataset.lon)], 15);
  }
}

async function geocodeInput(inputId) {
  const input = document.getElementById(inputId);
  try {
    const res = await fetch(`/api/geocode?q=${encodeURIComponent(input.value + ' Oslo')}`);
    const data = await res.json();
    if (data.length) {
      let list = document.getElementById(inputId + 'List');
      if (!list) {
        list = document.createElement('div');
        list.id = inputId + 'List';
        input.closest('.search-wrapper').appendChild(list);
      }
      list._results = data;
      selectSuggestion(inputId, 0);
    }
  } catch (e) {}
}

// ─── RUTE ─────────────────────────────────────────────────────
async function drawRoute() {
  const from = document.getElementById('fromInput');
  const to = document.getElementById('toInput');
  if (!from.dataset.lat || !to.dataset.lat) return;

  clearRoute();

  try {
    const res = await fetch(
      `/api/route?from_lon=${from.dataset.lon}&from_lat=${from.dataset.lat}&to_lon=${to.dataset.lon}&to_lat=${to.dataset.lat}`
    );
    const data = await res.json();
    if (!data.routes?.length) return;

    const coords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
    const durationMin = Math.round(data.routes[0].duration / 60);
    const distKm = (data.routes[0].distance / 1000).toFixed(1);
    const h = (new Date().getHours() + currentHourOffset) % 24;
    const isRush = (h >= 7 && h <= 9) || (h >= 15 && h <= 18);
    const adjustedMin = isRush ? Math.round(durationMin * 1.6) : durationMin;

    routeLayer = L.polyline(coords, {
      color: COLORS[isRush ? 3 : 1],
      weight: 7,
      opacity: 0.95
    }).addTo(map);

    map.fitBounds(routeLayer.getBounds(), { padding: [60, 60] });

    const markerHtml = color =>
      `<div style="width:14px;height:14px;background:${color};border-radius:50%;border:3px solid #0a0a0f;box-shadow:0 0 8px ${color}"></div>`;

    routeMarkers.push(
      L.marker([from.dataset.lat, from.dataset.lon], {
        icon: L.divIcon({ className: '', html: markerHtml('#00ff88') })
      }).addTo(map),
      L.marker([to.dataset.lat, to.dataset.lon], {
        icon: L.divIcon({ className: '', html: markerHtml('#ff4d00') })
      }).addTo(map)
    );

    document.getElementById('travelTime').textContent = adjustedMin + ' min';
    document.getElementById('travelSub').textContent =
      `Bil · ${distKm} km · ${isRush ? 'Rushtid 🔴' : 'Normal 🟢'}`;
    const clrBtn = document.getElementById('clearRouteBtn');
    if (clrBtn) clrBtn.style.display = 'flex';
  } catch (e) {
    console.log('Rute-feil:', e);
  }
}

function clearRoute() {
  if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
  routeMarkers.forEach(m => map.removeLayer(m));
  routeMarkers = [];
  document.getElementById('travelTime').textContent = '-- min';
  document.getElementById('travelSub').textContent = 'Velg rute for estimat';
  const clrBtn = document.getElementById('clearRouteBtn');
  if (clrBtn) clrBtn.style.display = 'none';
}

// ─── MIN POSISJON ─────────────────────────────────────────────
async function geolocate(inputId) {
  if (!navigator.geolocation) return;
  const input = document.getElementById(inputId);
  const origPlaceholder = input.placeholder;
  input.placeholder = 'Finner posisjon...';
  navigator.geolocation.getCurrentPosition(async pos => {
    const { latitude: lat, longitude: lon } = pos.coords;
    input.dataset.lat = lat;
    input.dataset.lon = lon;
    try {
      const res = await fetch(`/api/reverse-geocode?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}`);
      const data = await res.json();
      input.value = data.display_name?.split(',').slice(0, 2).join(', ') || 'Min posisjon';
    } catch {
      input.value = 'Min posisjon';
    }
    input.placeholder = origPlaceholder;
    map.setView([lat, lon], 14);
    const from = document.getElementById('fromInput');
    const to = document.getElementById('toInput');
    if (from.dataset.lat && to.dataset.lat) drawRoute();
  }, () => { input.placeholder = origPlaceholder; });
}

// ─── SLIDER ───────────────────────────────────────────────────
const timeSlider = document.getElementById('timeSlider');
const timeDisplay = document.getElementById('timeDisplay');

timeSlider.addEventListener('input', () => {
  const val = parseInt(timeSlider.value);
  const offset = val * 0.5;
  currentHourOffset = offset;
  if (val === 0) {
    timeDisplay.textContent = 'NÅ';
  } else {
    const t = new Date(Date.now() + val * 1800000);
    const hh = String(t.getHours()).padStart(2, '0');
    const mm = String(t.getMinutes()).padStart(2, '0');
    const totalMins = val * 30;
    const lh = Math.floor(totalMins / 60);
    const lm = totalMins % 60;
    const label = lh === 0 ? `+${lm}min` : lm === 0 ? `+${lh}t` : `+${lh}t ${lm}min`;
    timeDisplay.textContent = `${label} (${hh}:${mm})`;
  }
  if (roadData) renderRoads(roadData, offset);
  if (routeLayer) {
    const h = (new Date().getHours() + offset) % 24;
    const isRush = (h >= 7 && h <= 9) || (h >= 15 && h <= 18);
    routeLayer.setStyle({ color: COLORS[isRush ? 3 : 1] });
    const sub = document.getElementById('travelSub');
    const match = sub?.textContent.match(/Bil · ([\d.]+) km/);
    if (match) sub.textContent = `Bil · ${match[1]} km · ${isRush ? 'Rushtid 🔴' : 'Normal 🟢'}`;
  }
});

// ─── MODAL ────────────────────────────────────────────────────
function openModal() { document.getElementById('modal').classList.add('open'); }
function closeModal() { document.getElementById('modal').classList.remove('open'); }

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

['mTime', 'mReturn', 'mWeather'].forEach(id =>
  document.getElementById(id).addEventListener('input', updateModal)
);

function updateModal() {
  const h = parseInt(document.getElementById('mTime').value);
  const ret = parseInt(document.getElementById('mReturn').value);
  const weather = parseInt(document.getElementById('mWeather').value);
  document.getElementById('mTimeVal').textContent = String(h).padStart(2, '0') + ':00';
  document.getElementById('mReturnVal').textContent = ret ? 'Ja' : 'Nei';
  document.getElementById('mWeatherVal').textContent = ['Ignorerer', 'Middels', 'Viktig'][weather];

  const isRush = (h >= 7 && h <= 9) || (h >= 15 && h <= 18);
  const carMins = isRush ? 35 + weather * 5 : 15;
  const busMins = 22;
  const busWins = busMins < carMins;

  document.getElementById('opt1').className = 'modal-option' + (busWins ? ' winner' : '');
  document.getElementById('opt1Icon').textContent = busWins ? '🚇' : '🚗';
  document.getElementById('opt1Icon').className = 'option-icon ' + (busWins ? 'bus' : 'car');
  document.getElementById('opt1Label').textContent = busWins ? 'Ta kollektivt' : 'Kjør bil';
  document.getElementById('opt1Detail').textContent = busWins
    ? `T-bane · ${busMins} min · Slipper kø`
    : `Ring 1 · ${carMins} min · Lite kø`;

  document.getElementById('opt2').className = 'modal-option' + (!busWins ? ' winner' : '');
  document.getElementById('opt2Icon').textContent = busWins ? '🚗' : '🚇';
  document.getElementById('opt2Icon').className = 'option-icon ' + (busWins ? 'car' : 'bus');
  document.getElementById('opt2Label').textContent = busWins ? 'Kjør bil' : 'Ta kollektivt';
  document.getElementById('opt2Detail').textContent = busWins
    ? `Ring 1 · ${carMins} min · ${isRush ? 'Mye kø' : 'Normal'}`
    : `T-bane · ${busMins} min`;
}

function swapAddresses() {
  const f = document.getElementById('fromInput');
  const t = document.getElementById('toInput');
  [f.value, t.value] = [t.value, f.value];
  [f.dataset.lat, t.dataset.lat] = [t.dataset.lat, f.dataset.lat];
  [f.dataset.lon, t.dataset.lon] = [t.dataset.lon, f.dataset.lon];
  if (f.dataset.lat && t.dataset.lat) drawRoute();
}

// ─── VÆR ──────────────────────────────────────────────────────
async function loadWeather() {
  try {
    const res = await fetch('/api/weather');
    const data = await res.json();
    const ts = data.properties.timeseries[0];
    const d = ts.data.instant.details;
    const precip = ts.data.next_1_hours?.details?.precipitation_amount || 0;
    weatherData = { temperature: d.air_temperature, precipitation: precip, wind_speed: d.wind_speed };
    document.getElementById('weatherTemp').textContent = Math.round(d.air_temperature) + '°C';
    const icon = precip > 1 ? '🌧' : precip > 0.1 ? '🌦' : d.air_temperature < 0 ? '❄️' : d.air_temperature > 20 ? '☀️' : '🌤';
    document.getElementById('weatherDesc').textContent = icon + ' ' + Math.round(d.wind_speed) + ' m/s';
    if (roadData && trafficLayerOn) renderRoads(roadData, currentHourOffset);
  } catch (e) {
    document.getElementById('weatherDesc').textContent = '–';
  }
}

// ─── START ────────────────────────────────────────────────────
loadWeather();
loadRoads();
setInterval(loadWeather, 600000);
