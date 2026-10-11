/**
 * AI-Powered Smart PDS - Inventory Controller
 * Compact layout, 4 KPI cards, 8-column tabular view, and responsive stock adjustments.
 */

let inventoryAlertsData = [];

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

document.addEventListener('DOMContentLoaded', async () => {
  await populateInventoryCommodityDropdowns();
  await loadInventoryData();

  const adjustForm = document.getElementById('adjust-stock-form');
  if (adjustForm) {
    adjustForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const com = document.getElementById('adjust-commodity').value;
      const reg = document.getElementById('adjust-region').value;
      const stock = parseFloat(document.getElementById('adjust-new-stock').value);

      if (isNaN(stock) || stock < 0) {
        showToast('Stock level must be a non-negative number.', 'error');
        return;
      }

      try {
        const res = await API.updateInventoryStock(com, reg, stock);
        if (res && res.status === 'success') {
          showToast(`Stock updated: ${com} in ${reg} set to ${stock.toLocaleString()} kg`, 'success');
          closeModal('adjust-stock-modal');
          adjustForm.reset();
          await loadInventoryData();
        }
      } catch (err) {
        showToast(err.message || 'Error updating stock', 'error');
      }
    });
  }
});

async function loadInventoryData() {
  try {
    const res = await API.getInventoryAlerts();
    if (res && res.status === 'success') {
      inventoryAlertsData = res.data || [];
      updateInventoryKPIs(inventoryAlertsData);
      renderInventoryTable(inventoryAlertsData);
    }
  } catch (err) {
    showToast('Failed to load inventory alerts', 'error');
  }
}

/**
 * Computes and renders exactly four summary cards:
 * 1. Total Stock
 * 2. Shortages
 * 3. Procurement Required
 * 4. Sufficient Stock
 */
function updateInventoryKPIs(data) {
  let totalStock = 0;
  let totalShortage = 0;
  let shortageCount = 0;
  let sufficientCount = 0;

  data.forEach(item => {
    totalStock += (item.current_stock || 0);
    if (item.shortage > 0 || item.status === 'SHORTAGE') {
      totalShortage += (item.shortage || 0);
      shortageCount++;
    } else {
      sufficientCount++;
    }
  });

  const elTotal = document.getElementById('inv-total-stock');
  const elShortage = document.getElementById('inv-shortage-count');
  const elProcurement = document.getElementById('inv-total-procurement');
  const elSufficient = document.getElementById('inv-sufficient-count');

  if (elTotal) elTotal.innerHTML = `${Math.round(totalStock).toLocaleString()} <span style="font-size:0.95rem;">kg</span>`;
  if (elShortage) elShortage.textContent = shortageCount;
  if (elProcurement) elProcurement.innerHTML = `${Math.round(totalShortage).toLocaleString()} <span style="font-size:0.95rem;">kg</span>`;
  if (elSufficient) elSufficient.textContent = sufficientCount;
}

/**
 * Renders compact table with 8 columns:
 * Commodity, District, Current Stock, Predicted Demand, Difference, Status, Procurement, Actions.
 * Replaces lengthy AI text with concise messages like "Shortage: 133 kg".
 */
function renderInventoryTable(items) {
  const tbody = document.getElementById('inventory-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:2rem;">No inventory records match filters.</td></tr>';
    return;
  }

  tbody.innerHTML = items.map(item => {
    const delta = (item.current_stock || 0) - (item.predicted_demand || 0);
    const deltaStr = delta >= 0 ? `+${Math.round(delta).toLocaleString()} kg` : `-${Math.round(Math.abs(delta)).toLocaleString()} kg`;
    const deltaColor = delta >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';

    // Concise status message replaces lengthy AI paragraph
    let statusBadge = '';
    if (item.status === 'SHORTAGE' || item.shortage > 0) {
      const shortageQty = Math.round(item.shortage || Math.abs(delta));
      statusBadge = `<span class="badge badge-danger">Shortage: ${shortageQty.toLocaleString()} kg</span>`;
    } else if (item.status === 'EXCESS') {
      statusBadge = `<span class="badge badge-info">Excess (+${Math.round(delta).toLocaleString()} kg)</span>`;
    } else {
      statusBadge = '<span class="badge badge-success">Sufficient</span>';
    }

    const procurementStr = item.recommended_procurement > 0
      ? `<strong style="color: var(--accent-rose);">${Math.round(item.recommended_procurement).toLocaleString()} kg</strong>`
      : '<span style="color: var(--text-muted);">-</span>';

    return `
      <tr>
        <td><strong>${escapeHtml(item.commodity)}</strong></td>
        <td><span class="badge badge-secondary">${escapeHtml(item.region)}</span></td>
        <td class="text-right"><strong>${Math.round(item.current_stock).toLocaleString()} kg</strong></td>
        <td class="text-right">${Math.round(item.predicted_demand).toLocaleString()} kg</td>
        <td class="text-right" style="color:${deltaColor}; font-weight:600;">${deltaStr}</td>
        <td class="text-center">${statusBadge}</td>
        <td class="text-right">${procurementStr}</td>
        <td class="text-center">
          <button class="btn btn-secondary btn-sm" title="Edit Stock Level" onclick="openQuickAdjust('${escapeHtml(item.commodity)}', '${escapeHtml(item.region)}', ${item.current_stock})">
            <i class="fa-solid fa-pen-to-square"></i> Edit
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function filterInventory() {
  const reg = document.getElementById('inv-filter-region').value;
  const com = document.getElementById('inv-filter-commodity').value;

  const filtered = inventoryAlertsData.filter(item => {
    const matchReg = !reg || item.region === reg;
    const matchCom = !com || item.commodity === com;
    return matchReg && matchCom;
  });

  renderInventoryTable(filtered);
}

function openQuickAdjust(commodity, region, currentStock) {
  const comSelect = document.getElementById('adjust-commodity');
  const regSelect = document.getElementById('adjust-region');
  const stockInput = document.getElementById('adjust-new-stock');

  if (comSelect) comSelect.value = commodity;
  if (regSelect) regSelect.value = region;
  if (stockInput) {
    stockInput.value = currentStock;
    setTimeout(() => stockInput.focus(), 100);
  }
  openModal('adjust-stock-modal');
}

async function populateInventoryCommodityDropdowns() {
  const filterSelect = document.getElementById('inv-filter-commodity');
  const adjustSelect = document.getElementById('adjust-commodity');
  try {
    const res = await API.getCommodities();
    if (res && res.status === 'success' && res.data && res.data.length > 0) {
      if (filterSelect) {
        const cur = filterSelect.value;
        filterSelect.innerHTML = '<option value="">All Commodities</option>' + res.data.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.commodity_code)})</option>`).join('');
        filterSelect.value = cur;
      }
      if (adjustSelect) {
        adjustSelect.innerHTML = res.data.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.commodity_code)})</option>`).join('');
      }
    }
  } catch (e) {
    console.warn('Could not populate inventory commodity dropdowns:', e);
  }
}
