import { formatBRL } from './api.js';

export function renderHeader(generatedAt, stores) {
  if (generatedAt) {
    const dt = new Date(generatedAt);
    const dateStr = dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
    const timeStr = dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    document.getElementById('last-updated').textContent = `Atualizado ${dateStr} às ${timeStr}`;
  }

  const activeStores = stores.filter((s) => s.items_found > 0).length;
  document.getElementById('health-label').textContent = `${activeStores}/${stores.length} lojas`;
  document.getElementById('health-dot').style.background =
    activeStores > 0 ? 'var(--green)' : 'var(--amber)';

  const list = document.getElementById('store-list');
  list.innerHTML = stores
    .map((s) => {
      const isBlocked = (s.errors || []).some((e) => e.includes('WAF_IP_BLOCKED'));
      const statusText =
        s.items_found > 0
          ? `<span style="color: var(--green); font-weight: 600;">${s.items_found} itens</span>`
          : isBlocked
            ? `<span style="color: var(--amber);">Bloqueio IP</span>`
            : `<span style="color: var(--text-tertiary);">0 itens</span>`;
      return `<div class="store-row"><span>${s.store}</span>${statusText}</div>`;
    })
    .join('');
}

export function renderAlerts(alerts) {
  const section = document.getElementById('alerts-section');
  const container = document.getElementById('alerts-list');

  if (!alerts || alerts.length === 0) {
    section.hidden = true;
    return;
  }

  section.hidden = false;
  container.innerHTML = alerts
    .slice(0, 6)
    .map((a) => {
      const dt = new Date(a.timestamp);
      const timeStr = dt.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });

      if (a.type === 'price_drop') {
        const pct = Number(a.drop_percent || 0).toFixed(1).replace('.', ',');
        return `
          <a href="${a.url}" target="_blank" rel="noopener" class="alert-card tabular">
            <div>
              <div class="alert-top">
                <span class="badge badge-drop">-${pct}% vs. mínima</span>
                <span class="alert-time">${timeStr}</span>
              </div>
              <div class="alert-beer" style="margin-top: 8px;">${a.group_name}</div>
              <div class="alert-store">${a.store} • ${a.title}</div>
            </div>
            <div class="alert-pricing">
              <div>
                <strong style="color: var(--green);">${formatBRL(a.current_ppl)}/L</strong>
                <span class="alert-prev" style="margin-left: 6px;">${formatBRL(a.previous_min_ppl)}/L</span>
              </div>
              <span style="font-weight: 600;">${formatBRL(a.current_price)}</span>
            </div>
          </a>
        `;
      }

      return `
        <a href="${a.url}" target="_blank" rel="noopener" class="alert-card is-restock tabular">
          <div>
            <div class="alert-top">
              <span class="badge badge-out">Retorno ao estoque</span>
              <span class="alert-time">${timeStr}</span>
            </div>
            <div class="alert-beer" style="margin-top: 8px;">${a.group_name}</div>
            <div class="alert-store">${a.store} • ${a.title}</div>
          </div>
          <div class="alert-pricing">
            <span style="color: var(--text-secondary);">${a.current_ppl ? formatBRL(a.current_ppl) + '/L' : ''}</span>
            <span style="font-weight: 600;">${formatBRL(a.current_price)}</span>
          </div>
        </a>
      `;
    })
    .join('');
}

export function renderFilters(items, onBreweryChange) {
  const breweries = [...new Set(items.map((i) => i.brewery))].sort();
  const stores = [...new Set(items.map((i) => i.store))].sort();

  const nav = document.getElementById('brewery-nav');
  breweries.forEach((brewery) => {
    const btn = document.createElement('button');
    btn.className = 'pill';
    btn.textContent = brewery;
    btn.dataset.brewery = brewery;
    btn.addEventListener('click', () => {
      nav.querySelectorAll('.pill').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      onBreweryChange(brewery);
    });
    nav.appendChild(btn);
  });

  nav.querySelector('[data-brewery=""]').addEventListener('click', (e) => {
    nav.querySelectorAll('.pill').forEach((p) => p.classList.remove('active'));
    e.target.classList.add('active');
    onBreweryChange('');
  });

  const storeSelect = document.getElementById('filter-store');
  stores.forEach((store) => {
    storeSelect.insertAdjacentHTML('beforeend', `<option value="${store}">${store}</option>`);
  });
}

export function renderKPIs(items) {
  const available = items.filter((i) => i.available);
  const drops = available.filter((i) => i.is_price_drop);
  const byLiter = available
    .filter((i) => i.price_per_liter != null)
    .sort((a, b) => a.price_per_liter - b.price_per_liter);

  document.getElementById('kpi-available').textContent = available.length;
  document.getElementById('kpi-drops').textContent = drops.length;
  document.getElementById('kpi-best-liter').textContent = byLiter.length
    ? `${formatBRL(byLiter[0].price_per_liter)}/L`
    : '—';
}

export function renderCards(items) {
  const grid = document.getElementById('cards-grid');

  if (items.length === 0) {
    grid.innerHTML = `<div class="empty-state">Nenhum rótulo encontrado para os filtros selecionados.</div>`;
    return;
  }

  grid.innerHTML = items
    .map((item) => {
      const volStr = item.volume_ml
        ? `${item.quantity > 1 ? item.quantity + '× ' : ''}${
            item.volume_ml >= 1000 ? item.volume_ml / 1000 + 'L' : item.volume_ml + 'ml'
          }`
        : '';
      const metaParts = [item.store, volStr].filter(Boolean).join(' • ');

      let badgeHtml = '';
      if (!item.available) {
        badgeHtml = `<span class="badge badge-out">Esgotado</span>`;
      } else if (item.is_price_drop) {
        const pct = Number(item.drop_percent || 0).toFixed(0);
        badgeHtml = `<span class="badge badge-drop">-${pct}% Mínima</span>`;
      }

      const imgHtml = item.image
        ? `<img src="${item.image}" alt="${item.title}" loading="lazy" />`
        : `<span class="card-media-placeholder">${item.brewery}</span>`;

      return `
        <article class="card ${!item.available ? 'sold-out' : ''}">
          <div>
            <div class="card-top">
              <span class="eyebrow">${item.brewery}</span>
              ${badgeHtml}
            </div>
            <div class="card-media">${imgHtml}</div>
            <h3 class="card-title" title="${item.title}">${item.title}</h3>
            <p class="card-meta">${metaParts}</p>
          </div>

          <div class="card-footer tabular">
            <div>
              <div class="price-main">${formatBRL(item.price)}</div>
              <div class="price-sub">${
                item.price_per_liter ? formatBRL(item.price_per_liter) + ' / litro' : '&nbsp;'
              }</div>
            </div>
            <div class="card-actions">
              <button class="btn-history" type="button" data-history-id="${item.id}">Histórico</button>
              <a class="btn-buy" href="${item.url}" target="_blank" rel="noopener">Ver</a>
            </div>
          </div>
        </article>
      `;
    })
    .join('');
}
