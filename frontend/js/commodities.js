/** Smart PDS commodity catalog controller. */
let allCommodities = [];
let targetDeleteCommodityCode = null;

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
}

const categoryFields = {
  AAY: ['new-com-price-aay', 'edit-com-price-aay'],
  PHH: ['new-com-price-phh', 'edit-com-price-phh'],
  NPHH: ['new-com-price-nphh', 'edit-com-price-nphh']
};

document.addEventListener('DOMContentLoaded', async () => {
  wirePreviews();
  await loadCommodities();
  document.getElementById('add-commodity-form')?.addEventListener('submit', createCommodityFromForm);
  document.getElementById('edit-commodity-form')?.addEventListener('submit', updateCommodityFromForm);
  document.getElementById('btn-confirm-delete-commodity')?.addEventListener('click', deleteCommodity);
});

function wirePreviews() {
  const ids = ['new-com-code', 'new-com-name', 'new-com-unit', 'new-com-scheme', 'new-com-market-price', 'new-com-desc', ...Object.values(categoryFields).map(fields => fields[0])];
  ids.forEach(id => document.getElementById(id)?.addEventListener('input', updateAddPreview));
  ['edit-com-name', 'edit-com-unit', 'edit-com-scheme', 'edit-com-market-price', 'edit-com-desc', ...Object.values(categoryFields).map(fields => fields[1])]
    .forEach(id => document.getElementById(id)?.addEventListener('input', updateEditPreview));
  document.getElementById('new-com-scheme')?.addEventListener('change', updateAddPreview);
  document.getElementById('edit-com-scheme')?.addEventListener('change', updateEditPreview);
}

function getCategoryPrices(prefix) {
  const suffix = prefix === 'new' ? 0 : 1;
  const values = {};
  for (const [category, fields] of Object.entries(categoryFields)) {
    const raw = document.getElementById(fields[suffix])?.value ?? '';
    values[category] = raw === '' ? null : Number(raw);
  }
  return values;
}

function schemeLabel(value) {
  return ({ NFSA: 'NFSA', TAMIL_NADU_STATE_PDS: 'Tamil Nadu State PDS', DEMO_CUSTOM: 'Demo / Custom' })[value] || 'Unclassified';
}

function renderPreview(targetId, record) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const isDemo = record.scheme_classification === 'DEMO_CUSTOM';
  const unit = escapeHtml(record.unit || 'unit');
  const rates = Object.entries(record.category_pricing || {})
    .map(([key, value]) => {
      if (value === null || !Number.isFinite(value)) return `${key}: Missing`;
      if (Number(value) === 0) return `${key}: FREE (₹0.00)/${unit}`;
      return `${key}: ₹${value.toFixed(2)}/${unit}${isDemo ? ' (Demo)' : ''}`;
    })
    .join(' · ');
  const benchmark = record.market_price === null || !Number.isFinite(record.market_price) ? 'Not provided' : `₹${record.market_price.toFixed(2)}/${unit}`;
  target.innerHTML = `<strong>${escapeHtml(record.commodity_code || 'New code')} · ${escapeHtml(record.name || 'New commodity')}</strong><br>${escapeHtml(schemeLabel(record.scheme_classification))}${isDemo ? ' <span class="badge badge-warning" style="font-size:0.65rem;">Demo</span>' : ''}<br>${rates}<br>Recorded benchmark: ${benchmark}<br>${escapeHtml(record.description || 'No description')}`;
}

function updateAddPreview() {
  renderPreview('new-com-preview', {
    commodity_code: document.getElementById('new-com-code')?.value.trim().toUpperCase(),
    name: document.getElementById('new-com-name')?.value.trim(),
    unit: document.getElementById('new-com-unit')?.value.trim(),
    scheme_classification: document.getElementById('new-com-scheme')?.value,
    category_pricing: getCategoryPrices('new'),
    market_price: document.getElementById('new-com-market-price')?.value === '' ? null : Number(document.getElementById('new-com-market-price')?.value),
    description: document.getElementById('new-com-desc')?.value.trim()
  });
}

function updateEditPreview() {
  renderPreview('edit-com-preview', {
    commodity_code: document.getElementById('edit-com-code')?.value,
    name: document.getElementById('edit-com-name')?.value.trim(),
    unit: document.getElementById('edit-com-unit')?.value.trim(),
    scheme_classification: document.getElementById('edit-com-scheme')?.value,
    category_pricing: getCategoryPrices('edit'),
    market_price: document.getElementById('edit-com-market-price')?.value === '' ? null : Number(document.getElementById('edit-com-market-price')?.value),
    description: document.getElementById('edit-com-desc')?.value.trim()
  });
}

function setCommoditiesLoadingState() {
  const tbody = document.getElementById('commodities-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="8" role="status" style="text-align:center;color:var(--text-muted);padding:3rem"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading commodity records from MongoDB…</td></tr>';
}

function setCommoditiesErrorState(message) {
  const tbody = document.getElementById('commodities-tbody');
  if (tbody) tbody.innerHTML = `<tr><td colspan="8" role="alert" style="text-align:center;color:var(--accent-rose);padding:3rem"><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(message || 'Commodity records could not be loaded.')} <button class="btn btn-secondary btn-sm" onclick="loadCommodities()">Retry</button></td></tr>`;
  ['com-kpi-total', 'com-kpi-official', 'com-kpi-demo', 'com-kpi-discount'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '--'; });
}

function setCommoditiesEmptyState(filtered) {
  const tbody = document.getElementById('commodities-tbody');
  if (!tbody) return;
  tbody.innerHTML = filtered
    ? '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:2.5rem">No matching commodities. Adjust the search or classification filter.</td></tr>'
    : '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:2.5rem">No commodity records are stored. Use Add Commodity to register one.</td></tr>';
}

async function loadCommodities() {
  setCommoditiesLoadingState();
  try {
    const res = await API.getCommodities();
    if (!res || res.status !== 'success' || !Array.isArray(res.data)) throw new Error(res?.message || 'Invalid commodity response');
    allCommodities = res.data;
    updateCommodityKPIs(res.summary || {});
    filterCommodities();
  } catch (error) {
    console.error('Could not load commodity catalog:', error);
    setCommoditiesErrorState(error.message);
    showToast(error.message || 'Could not load commodity records', 'error');
  }
}

async function refreshCommodities() {
  const button = document.getElementById('btn-refresh-commodities');
  if (button) button.disabled = true;
  try { await loadCommodities(); }
  finally { if (button) button.disabled = false; }
}

function updateCommodityKPIs(summary) {
  const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  setText('com-kpi-total', Number(summary.total_count ?? 0).toLocaleString());
  setText('com-kpi-official', Number(summary.official_count ?? 0).toLocaleString());
  setText('com-kpi-demo', Number(summary.demo_count ?? 0).toLocaleString());
  const avg = summary.average_subsidy_discount;
  setText('com-kpi-discount', avg === null || avg === undefined ? '—' : `${Number(avg).toFixed(1)}%`);
}

function resetCommodityFilters() {
  document.getElementById('com-search').value = '';
  document.getElementById('com-filter-rate').value = '';
  filterCommodities();
}

function filterCommodities() {
  const term = (document.getElementById('com-search')?.value || '').trim().toLowerCase();
  const scheme = document.getElementById('com-filter-rate')?.value || '';
  const filtered = allCommodities.filter(c => {
    const matchesSearch = !term || [c.commodity_code, c.name, c.description, c.official_source]
      .some(value => String(value || '').toLowerCase().includes(term));
    return matchesSearch && (!scheme || c.scheme_classification === scheme);
  });
  if (filtered.length) renderCommoditiesTable(filtered);
  else setCommoditiesEmptyState(allCommodities.length > 0);
}

function renderCommoditiesTable(items) {
  const tbody = document.getElementById('commodities-tbody');
  if (!tbody) return;
  tbody.innerHTML = items.map(c => {
    const categoryPrices = c.category_pricing || {};
    const isDemo = c.scheme_classification === 'DEMO_CUSTOM' || c.is_demonstration;
    const unit = escapeHtml(c.unit || 'unit');

    const rates = ['AAY', 'PHH', 'NPHH'].map(category => {
      const price = categoryPrices[category];
      const discount = c.category_discounts?.[category];
      const saving = c.category_savings?.[category];

      let priceHtml = '';
      let discountHtml = '';

      if (price === undefined || price === null || !Number.isFinite(Number(price))) {
        priceHtml = '<span style="color:var(--text-muted); font-style:italic;">Missing / Not recorded</span>';
      } else if (Number(price) === 0) {
        priceHtml = `<span class="badge badge-success" style="font-size:0.74rem;"><i class="fa-solid fa-gift"></i> FREE (₹0.00)</span>`;
        if (saving !== undefined && Number(saving) > 0) {
          discountHtml = `<small style="color:var(--text-muted); display:block; margin-top:2px;">100.0% subsidized (₹${Number(saving).toFixed(2)} savings)</small>`;
        }
      } else if (isDemo) {
        priceHtml = `<strong>₹${Number(price).toFixed(2)}</strong> <span style="font-size:0.75rem; color:var(--text-secondary);">/ ${unit}</span> <span class="badge badge-warning" style="font-size:0.65rem;"><i class="fa-solid fa-flask"></i> Demo Rate</span>`;
        if (discount !== undefined) {
          discountHtml = `<small style="color:var(--text-muted); display:block; margin-top:2px;">${discount.toFixed(1)}% vs benchmark (₹${Number(saving).toFixed(2)})</small>`;
        }
      } else {
        priceHtml = `<strong>₹${Number(price).toFixed(2)} / ${unit}</strong>`;
        if (discount !== undefined) {
          discountHtml = `<small style="color:var(--text-muted); display:block; margin-top:2px;">${discount.toFixed(1)}% below benchmark (₹${Number(saving).toFixed(2)})</small>`;
        }
      }

      const catBadge = category === 'AAY' ? 'badge-purple' : (category === 'PHH' ? 'badge-info' : 'badge-secondary');
      return `
        <div class="commodity-rate">
          <span class="badge ${catBadge}" style="font-weight:700;">${category}</span>
          <span style="text-align:right;">${priceHtml}${discountHtml}</span>
        </div>
      `;
    }).join('');

    const benchmark = c.market_price === null || c.market_price === undefined || !Number.isFinite(Number(c.market_price))
      ? '<span style="color:var(--text-muted); font-style:italic;">Not recorded</span>'
      : `<strong>₹${Number(c.market_price).toFixed(2)} / ${unit}</strong>`;

    const className = c.scheme_classification;
    const classLabel = schemeLabel(className);
    const classBadge = className === 'NFSA' ? 'badge-info' : className === 'TAMIL_NADU_STATE_PDS' ? 'badge-purple' : 'badge-warning';

    let verificationBadge = '';
    if (c.is_verified) {
      verificationBadge = '<span class="badge badge-success" title="Verified by official published authority"><i class="fa-solid fa-circle-check"></i> Verified Official</span>';
    } else if (c.scheme_classification === 'DEMO_CUSTOM') {
      verificationBadge = '<span class="badge badge-warning" title="Synthetic demo rate for simulation and testing"><i class="fa-solid fa-flask"></i> Demo / Synthetic</span>';
    } else {
      verificationBadge = '<span class="badge badge-secondary" title="No reliable official verification source provided"><i class="fa-solid fa-circle-question"></i> Unverified</span>';
    }

    const source = c.verification_source || c.official_source;
    let sourceHtml = '';
    if (source) {
      const isUrl = /^https?:\/\//i.test(source);
      if (isUrl) {
        sourceHtml = `<div style="font-size:0.7rem; margin-top:4px;"><a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent-cyan); text-decoration:underline;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Official Source</a></div>`;
      } else {
        sourceHtml = `<div style="font-size:0.72rem; color:var(--text-muted); margin-top:4px; line-height:1.3; overflow-wrap:anywhere;">${escapeHtml(source)}</div>`;
      }
    }

    return `<tr>
      <td><span style="font-weight:500; color:var(--text-primary); font-size:0.88rem;">${escapeHtml(c.commodity_code)}</span></td>
      <td><strong>${escapeHtml(c.name)}</strong>${c.description ? `<div style="font-size:0.75rem; color:var(--text-muted); margin-top:3px; line-height:1.3;">${escapeHtml(c.description)}</div>` : ''}</td>
      <td style="text-align:center;">${escapeHtml(c.unit || '—')}</td>
      <td><div class="commodity-rates">${rates}</div></td>
      <td>${benchmark}</td>
      <td><span class="badge ${classBadge} scheme-badge">${escapeHtml(classLabel)}</span><div style="margin-top:4px;">${verificationBadge}</div>${sourceHtml}</td>
      <td><div style="display:flex; flex-direction:column; gap:4px; align-items:flex-start;"><span class="badge badge-info">${Number(c.linked_inventory_count || 0)} Depots</span><span class="badge badge-purple">${Number(c.linked_transactions_count || 0)} Txns</span></div></td>
      <td style="text-align:right;"><div style="display:inline-flex; gap:6px; align-items:center; justify-content:flex-end;"><button class="btn btn-secondary btn-sm" onclick="openConfigureCommodity('${escapeHtml(c.commodity_code)}')" title="Edit"><i class="fa-solid fa-sliders"></i></button><button class="btn btn-secondary btn-sm" onclick="confirmDeleteCommodity('${escapeHtml(c.commodity_code)}')" title="Delete" style="color:var(--accent-rose);"><i class="fa-solid fa-trash-can"></i></button></div></td>
    </tr>`;
  }).join('');
}

function getPricePayload(prefix) {
  const id = category => `${prefix}-com-price-${category.toLowerCase()}`;
  return { AAY: Number(document.getElementById(id('AAY')).value), PHH: Number(document.getElementById(id('PHH')).value), NPHH: Number(document.getElementById(id('NPHH')).value) };
}

function validateFormPrices(prices, benchmark) {
  if (Object.values(prices).some(value => !Number.isFinite(value) || value < 0)) return 'All category issue prices must be valid non-negative numbers.';
  if (benchmark !== null && (!Number.isFinite(benchmark) || benchmark < 0)) return 'Benchmark must be a valid non-negative number.';
  if (benchmark !== null && Object.values(prices).some(price => benchmark < price)) return 'Benchmark cannot be lower than any category issue price.';
  return '';
}

async function createCommodityFromForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const code = document.getElementById('new-com-code').value.trim().toUpperCase();
  const name = document.getElementById('new-com-name').value.trim();
  const benchmarkRaw = document.getElementById('new-com-market-price').value;
  const benchmark = benchmarkRaw === '' ? null : Number(benchmarkRaw);
  const prices = getPricePayload('new');
  const validation = validateFormPrices(prices, benchmark);
  if (validation) return showToast(validation, 'error');
  const payload = {
    commodity_code: code, name, unit: document.getElementById('new-com-unit').value.trim(),
    scheme_classification: document.getElementById('new-com-scheme').value,
    category_pricing: prices, market_price: benchmark,
    description: document.getElementById('new-com-desc').value.trim()
  };
  try {
    const res = await API.createCommodity(payload);
    if (res?.status === 'success') {
      showToast(`Commodity ${code} saved to MongoDB.`, 'success');
      closeModal('add-commodity-modal'); form.reset();
      document.getElementById('new-com-unit').value = 'kg'; updateAddPreview();
      await loadCommodities();
    }
  } catch (error) { showToast(error.message || 'Could not create commodity', 'error'); }
}

async function updateCommodityFromForm(event) {
  event.preventDefault();
  const code = document.getElementById('edit-com-code').value;
  const benchmarkRaw = document.getElementById('edit-com-market-price').value;
  const benchmark = benchmarkRaw === '' ? null : Number(benchmarkRaw);
  const prices = getPricePayload('edit');
  const validation = validateFormPrices(prices, benchmark);
  if (validation) return showToast(validation, 'error');
  try {
    const res = await API.updateCommodity(code, {
      name: document.getElementById('edit-com-name').value.trim(),
      unit: document.getElementById('edit-com-unit').value.trim(),
      scheme_classification: document.getElementById('edit-com-scheme').value,
      category_pricing: prices, market_price: benchmark,
      description: document.getElementById('edit-com-desc').value.trim()
    });
    if (res?.status === 'success') {
      showToast(`Commodity ${code} updated in MongoDB. Verification was cleared for review.`, 'success');
      closeModal('edit-commodity-modal'); await loadCommodities();
    }
  } catch (error) { showToast(error.message || 'Could not update commodity', 'error'); }
}

function openConfigureCommodity(code) {
  const c = allCommodities.find(item => item.commodity_code === code);
  if (!c) return showToast(`Commodity ${code} not found`, 'error');
  document.getElementById('edit-com-code').value = c.commodity_code;
  document.getElementById('edit-com-name').value = c.name || '';
  document.getElementById('edit-com-unit').value = c.unit || '';
  document.getElementById('edit-com-scheme').value = c.scheme_classification || 'DEMO_CUSTOM';
  document.getElementById('edit-com-market-price').value = c.market_price ?? '';
  document.getElementById('edit-com-desc').value = c.description || '';
  const prices = c.category_pricing || {};
  for (const category of ['AAY', 'PHH', 'NPHH']) document.getElementById(`edit-com-price-${category.toLowerCase()}`).value = prices[category] ?? '';
  updateEditPreview(); openModal('edit-commodity-modal');
}

function confirmDeleteCommodity(code) {
  const c = allCommodities.find(item => item.commodity_code === code);
  if (!c) return;
  targetDeleteCommodityCode = code;
  document.getElementById('delete-com-target-name').textContent = `${c.commodity_code} (${c.name})`;
  const warning = document.getElementById('delete-com-linkage-warning');
  const inv = Number(c.linked_inventory_count || 0), txns = Number(c.linked_transactions_count || 0);
  warning.style.display = inv || txns ? 'block' : 'none';
  warning.textContent = inv || txns ? `Deletion will be blocked: linked to ${inv} inventory record(s) and ${txns} transaction(s).` : '';
  openModal('delete-commodity-modal');
}

async function deleteCommodity(event) {
  if (!targetDeleteCommodityCode) return;
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const res = await API.deleteCommodity(targetDeleteCommodityCode);
    if (res?.status === 'success') {
      showToast(`Commodity ${targetDeleteCommodityCode} deleted.`, 'success');
      closeModal('delete-commodity-modal'); targetDeleteCommodityCode = null;
      await loadCommodities();
    }
  } catch (error) { showToast(error.message || 'Deletion rejected by server', 'error'); }
  finally { button.disabled = false; }
}

// Compatibility aliases for links in older pages/scripts.
function openEditCommodityModal(code) { openConfigureCommodity(code); }
function promptDeleteCommodity(code) { confirmDeleteCommodity(code); }
