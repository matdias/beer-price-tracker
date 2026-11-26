import { formatBRL } from './api.js';

let chartInstance = null;

export function setupDrawer(getItemById, getHistoryRows) {
  const backdrop = document.getElementById('drawer-backdrop');
  const drawer = document.getElementById('history-drawer');
  const closeBtn = document.getElementById('drawer-close');
  const grid = document.getElementById('cards-grid');

  const close = () => {
    backdrop.classList.remove('open');
    drawer.classList.remove('open');
  };

  closeBtn.addEventListener('click', close);
  backdrop.addEventListener('click', close);

  // Event delegation para os botões "Histórico" nos cards
  grid.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-history-id]');
    if (!btn) return;
    const item = getItemById(btn.dataset.historyId);
    if (item) openDrawer(item, getHistoryRows());
  });
}

function openDrawer(item, historyRows) {
  const points = historyRows
    .filter((r) => r.id === item.id && parseFloat(r.price) > 0)
    .map((r) => ({
      label: new Date(r.timestamp).toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }),
      price: parseFloat(r.price),
    }));

  document.getElementById('drawer-eyebrow').textContent = `${item.brewery} • ${item.store}`;
  document.getElementById('drawer-title').textContent = item.title;
  document.getElementById('drawer-current').textContent = formatBRL(item.price);
  document.getElementById('drawer-min').textContent = formatBRL(item.historical_min ?? item.price);
  document.getElementById('drawer-link').href = item.url;

  const isDark = document.documentElement.classList.contains('dark');
  const lineColor = isDark ? '#c96a28' : '#a85118';
  const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
  const tickColor = '#86868b';


  const ctx = document.getElementById('history-chart').getContext('2d');
  if (chartInstance) chartInstance.destroy();

  chartInstance = new window.Chart(ctx, {
    type: 'line',
    data: {
      labels: points.map((p) => p.label),
      datasets: [
        {
          label: 'Preço (R$)',
          data: points.map((p) => p.price),
          borderColor: lineColor,
          backgroundColor: isDark ? 'rgba(201, 106, 40, 0.14)' : 'rgba(168, 81, 24, 0.12)',
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: 3.5,
          pointBackgroundColor: lineColor,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: tickColor, font: { family: 'Helvetica Neue, sans-serif', size: 11 } },
          grid: { display: false },
        },
        y: {
          ticks: {
            color: tickColor,
            font: { family: 'Helvetica Neue, sans-serif', size: 11 },
            callback: (v) => `R$ ${v}`,
          },
          grid: { color: gridColor },
        },
      },
    },
  });

  document.getElementById('drawer-backdrop').classList.add('open');
  document.getElementById('history-drawer').classList.add('open');
}
