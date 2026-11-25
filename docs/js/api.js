export const formatBRL = (value) =>
  value != null
    ? value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
    : '—';

export async function fetchDashboardData() {
  const cacheBust = `?t=${Date.now()}`;
  const [latestRes, logsRes, csvRes] = await Promise.all([
    fetch(`data/latest.json${cacheBust}`),
    fetch(`data/logs.json${cacheBust}`),
    fetch(`data/history.csv${cacheBust}`),
  ]);

  if (!latestRes.ok) {
    throw new Error('Falha ao carregar latest.json');
  }

  const latestData = await latestRes.json();
  const logsData = logsRes.ok ? await logsRes.json() : { stores: [] };
  const csvText = csvRes.ok ? await csvRes.text() : '';
  const historyRows = window.Papa
    ? window.Papa.parse(csvText, { header: true, skipEmptyLines: true }).data
    : [];

  return {
    generatedAt: latestData.generated_at,
    items: latestData.items || [],
    stores: logsData.stores || [],
    historyRows,
  };
}
