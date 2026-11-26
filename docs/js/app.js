import { fetchDashboardData } from './api.js';
import { renderHeader, renderAlerts, renderFilters, renderKPIs, renderCards } from './render.js';
import { setupDrawer } from './drawer.js';

const state = {
  items: [],
  historyRows: [],
  selectedBrewery: '',
};

function setupUIControls() {
  const statusBtn = document.getElementById('status-btn');
  const statusPopover = document.getElementById('status-popover');
  statusBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    statusPopover.classList.toggle('open');
  });
  document.addEventListener('click', () => statusPopover.classList.remove('open'));

  ['filter-search', 'filter-store', 'filter-available', 'sort-by'].forEach((id) => {
    const el = document.getElementById(id);
    el.addEventListener('input', applyFiltersAndRender);
    el.addEventListener('change', applyFiltersAndRender);
  });
}

function applyFiltersAndRender() {
  const query = document.getElementById('filter-search').value.toLowerCase().trim();
  const store = document.getElementById('filter-store').value;
  const onlyAvail = document.getElementById('filter-available').checked;
  const sortBy = document.getElementById('sort-by').value;

  const filtered = state.items.filter((item) => {
    if (onlyAvail && !item.available) return false;
    if (state.selectedBrewery && item.brewery !== state.selectedBrewery) return false;
    if (store && item.store !== store) return false;
    if (query && !`${item.title} ${item.brewery} ${item.store}`.toLowerCase().includes(query)) {
      return false;
    }
    return true;
  });

  filtered.sort((a, b) => {
    if (sortBy === 'price_asc') return a.price - b.price;
    if (sortBy === 'brewery_asc') {
      return (
        a.brewery.localeCompare(b.brewery) ||
        (a.price_per_liter ?? 9e9) - (b.price_per_liter ?? 9e9)
      );
    }
    if (sortBy === 'drop_first') {
      return (
        b.is_price_drop - a.is_price_drop ||
        (b.drop_percent || 0) - (a.drop_percent || 0) ||
        (a.price_per_liter ?? 9e9) - (b.price_per_liter ?? 9e9)
      );
    }
    return (a.price_per_liter ?? 9e9) - (b.price_per_liter ?? 9e9);
  });

  renderCards(filtered);
}

async function init() {
  setupUIControls();
  setupDrawer(
    (id) => state.items.find((i) => i.id === id),
    () => state.historyRows
  );

  try {
    const data = await fetchDashboardData();
    state.items = data.items;
    state.historyRows = data.historyRows;

    renderHeader(data.generatedAt, data.stores);
    renderAlerts(data.alerts);
    renderFilters(state.items, (brewery) => {
      state.selectedBrewery = brewery;
      applyFiltersAndRender();
    });
    renderKPIs(state.items);
    applyFiltersAndRender();
  } catch (err) {
    console.error(err);
    document.getElementById('last-updated').textContent = 'Aguardando primeira coleta';
  }
}

init();
