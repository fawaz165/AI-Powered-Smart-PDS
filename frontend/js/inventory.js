/**
 * AI-Powered Smart PDS - Inventory Controller
 * Real-time depot stock tracking, predictive replenishment, transparent procurement calculations,
 * and multi-district/commodity filtering synchronized with executive dashboard.
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

  // Modal dynamic stock pre-fill on dropdown change
  const adjustCom = document.getElementById('adjust-commodity');
  const adjustReg = document.getElementById('adjust-region');
  if (adjustCom && adjustReg) {
    adjustCom.addEventListener('change', syncModalCurrentStock);
    adjustReg.addEventListener('change', syncModalCurrentStock);
  }

  // Adjust stock form submission
  const adjustForm = document.getElementById('adjust-stock-form');
  if (adjustForm) {
    adjustForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const com = document.getElementById('adjust-commodity').value;
      const reg = document.getElementById('adjust-region').value;
      const rawStock = document.getElementById('adjust-new-stock').value;
      const stock = parseFloat(rawStock);

      if (rawStock.trim() === '' || isNaN(stock) || stock < 0) {
        showToast('Stock level must be a valid non-negative number (>= 0 kg).', 'error');
        return;
      }

      const submitBtn = adjustForm.querySelector('button[type="submit"]');
      const origBtnHtml = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
      }

      try {
        const res = await API.updateInventoryStock(com, reg, stock);
        if (res && res.status === 'success') {
          showToast(`Stock updated: ${com} in ${reg} set to ${stock.toLocaleString()} kg`, 'success');
          
          // Notify dashboard and sibling tabs of inventory update
          try {
            localStorage.setItem('smart_pds_inventory_updated', Date.now().toString());
          } catch (_) {}

          closeModal('adjust-stock-modal');
          adjustForm.reset();

          // Refresh data and keep active filter selection
          await loadInventoryData();
        } else {
          showToast(res.message || 'Failed to update stock level', 'error');
        }
      } catch (err) {
        showToast(err.message || 'Error updating stock level', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = origBtnHtml;
        }
      }
    });
  }

  // Auto-refresh when inventory updates occur in other tabs
  window.addEventListener('storage', (e) => {
    if (e.key === 'smart_pds_inventory_updated') {
      loadInventoryData();
    }
  });
});

/**
 * Pre-populates the modal input with current warehouse stock when selecting commodity or region.
 */
function syncModalCurrentStock() {
  const com = document.getElementById('adjust-commodity')?.value;
  const reg = document.getElementById('adjust-region')?.value;
  const stockInput = document.getElementById('adjust-new-stock');
  if (!com || !reg || !stockInput) return;

  const found = inventoryAlertsData.find(item =>
    item.region && item.region.toLowerCase() === reg.toLowerCase() &&
    (item.commodity.toLowerCase() === com.toLowerCase() || item.commodity_code === com)
  );

  if (found && found.current_stock !== undefined) {
    stockInput.value = found.current_stock;
  }
}

/**
 * Loads inventory alerts and telemetry from backend database.
 */
async function loadInventoryData() {
  try {
    const res = await API.getInventoryAlerts();
    if (res && res.status === 'success') {
      inventoryAlertsData = res.data || [];
      // Re-apply filters to maintain current user view
      filterInventory();
    } else {
      showToast('Could not retrieve live inventory records.', 'error');
    }
  } catch (err) {
    console.error('Error fetching inventory alerts:', err);
    showToast('Failed to load inventory alerts from server.', 'error');
  }
}

/**
 * Computes and renders exactly four summary cards with live database telemetry:
 * 1. Total Stock
 * 2. Shortages (Depots below demand)
 * 3. Procurement Required (Replenishment deficit)
 * 4. Sufficient Stock (Depots with adequate stock)
 */
function updateInventoryKPIs(data, regFilter = '', comFilter = '') {
  let totalStock = 0;
  let totalShortage = 0;
  let totalProcurement = 0;
  let shortageCount = 0;
  let sufficientCount = 0;

  data.forEach(item => {
    const cur = parseFloat(item.current_stock) || 0;
    const shortage = parseFloat(item.shortage) || 0;
    const proc = parseFloat(item.recommended_procurement) || 0;

    totalStock += cur;
    totalProcurement += proc;

    if (shortage > 0 || item.status === 'SHORTAGE') {
      totalShortage += shortage;
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
  if (elProcurement) elProcurement.innerHTML = `${Math.round(totalProcurement).toLocaleString()} <span style="font-size:0.95rem;">kg</span>`;
  if (elSufficient) elSufficient.textContent = sufficientCount;

  // Dynamic filter state descriptions
  const metaTotal = document.getElementById('inv-total-stock-meta');
  const metaShortage = document.getElementById('inv-shortage-meta');
  const metaProc = document.getElementById('inv-procurement-meta');
  const metaSufficient = document.getElementById('inv-sufficient-meta');

  let filterLabel = 'All 5 districts combined';
  if (regFilter && comFilter) {
    filterLabel = `Filtered: ${comFilter} in ${regFilter}`;
  } else if (regFilter) {
    filterLabel = `Filtered: ${regFilter} (All Commodities)`;
  } else if (comFilter) {
    filterLabel = `Filtered: ${comFilter} (All 5 Districts)`;
  }

  if (metaTotal) metaTotal.textContent = filterLabel;
  if (metaShortage) metaShortage.textContent = `${shortageCount} of ${data.length} depot${data.length === 1 ? '' : 's'} below demand`;
  if (metaProc) {
    metaProc.textContent = totalProcurement > 0 
      ? `Replenishment deficit: ${Math.round(totalProcurement).toLocaleString()} kg` 
      : 'Optimal (Zero deficit across selection)';
  }
  if (metaSufficient) metaSufficient.textContent = `${sufficientCount} of ${data.length} depot${data.length === 1 ? '' : 's'} adequate`;
}

/**
 * Renders compact table with 8 columns:
 * Commodity, District, Current Stock, Predicted Demand, Difference, Status, Procurement, Actions.
 */
function renderInventoryTable(items, regFilter = '', comFilter = '') {
  const tbody = document.getElementById('inventory-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    const filterDesc = (regFilter || comFilter) 
      ? ` for District: <strong>${escapeHtml(regFilter || 'All')}</strong>, Commodity: <strong>${escapeHtml(comFilter || 'All')}</strong>` 
      : '';
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:2rem;">No inventory records match filters${filterDesc}.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(item => {
    const curStock = parseFloat(item.current_stock) || 0;
    const predDemand = parseFloat(item.predicted_demand) || 0;
    const delta = curStock - predDemand;
    const deltaStr = delta >= 0 
      ? `+${Math.round(delta).toLocaleString()} kg` 
      : `-${Math.round(Math.abs(delta)).toLocaleString()} kg`;
    const deltaColor = delta >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';

    // Concise, auditable status badge
    let statusBadge = '';
    const shortageQty = parseFloat(item.shortage) || (delta < 0 ? Math.abs(delta) : 0);
    if (item.status === 'SHORTAGE' || shortageQty > 0) {
      statusBadge = `<span class="badge badge-danger">Shortage: ${Math.round(shortageQty).toLocaleString()} kg</span>`;
    } else if (item.status === 'EXCESS') {
      statusBadge = `<span class="badge badge-info">Excess (+${Math.round(delta).toLocaleString()} kg)</span>`;
    } else {
      statusBadge = '<span class="badge badge-success">Sufficient</span>';
    }

    const recProc = parseFloat(item.recommended_procurement) || 0;
    const procurementStr = recProc > 0
      ? `<strong style="color: var(--accent-rose);">${Math.round(recProc).toLocaleString()} kg</strong>`
      : '<span style="color: var(--text-muted);">-</span>';

    const commCode = item.commodity_code ? ` <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: normal;">(${escapeHtml(item.commodity_code)})</span>` : '';

    return `
      <tr>
        <td><strong>${escapeHtml(item.commodity)}</strong>${commCode}</td>
        <td><span class="badge badge-secondary">${escapeHtml(item.region)}</span></td>
        <td class="text-right"><strong>${Math.round(curStock).toLocaleString()} kg</strong></td>
        <td class="text-right">${Math.round(predDemand).toLocaleString()} kg</td>
        <td class="text-right" style="color:${deltaColor}; font-weight:600;">${deltaStr}</td>
        <td class="text-center">${statusBadge}</td>
        <td class="text-right">${procurementStr}</td>
        <td class="text-center">
          <button class="btn btn-secondary btn-sm" title="Edit Stock Level" onclick="openQuickAdjust('${escapeHtml(item.commodity)}', '${escapeHtml(item.region)}', ${curStock})">
            <i class="fa-solid fa-pen-to-square"></i> Edit
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * Filter inventory data by district and commodity in full mutual combination.
 */
function filterInventory() {
  const regSelect = document.getElementById('inv-filter-region');
  const comSelect = document.getElementById('inv-filter-commodity');
  const reg = (regSelect?.value || '').trim();
  const com = (comSelect?.value || '').trim();

  const filtered = inventoryAlertsData.filter(item => {
    const matchReg = !reg || (item.region && item.region.toLowerCase() === reg.toLowerCase());
    const matchCom = !com || 
      (item.commodity && item.commodity.toLowerCase() === com.toLowerCase()) || 
      (item.commodity_code && item.commodity_code.toUpperCase() === com.toUpperCase());
    return matchReg && matchCom;
  });

  updateInventoryKPIs(filtered, reg, com);
  renderInventoryTable(filtered, reg, com);
}

/**
 * Opens stock adjustment modal pre-populated with selected row data.
 */
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

/**
 * Populates filter and modal commodity dropdowns dynamically from commodity API.
 */
async function populateInventoryCommodityDropdowns() {
  const filterSelect = document.getElementById('inv-filter-commodity');
  const adjustSelect = document.getElementById('adjust-commodity');
  try {
    const res = await API.getCommodities();
    if (res && res.status === 'success' && res.data && res.data.length > 0) {
      if (filterSelect) {
        const cur = filterSelect.value;
        filterSelect.innerHTML = '<option value="">All Commodities</option>' + res.data.map(c => 
          `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.commodity_code)})</option>`
        ).join('');
        filterSelect.value = cur;
      }
      if (adjustSelect) {
        const curAdjust = adjustSelect.value;
        adjustSelect.innerHTML = res.data.map(c => 
          `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.commodity_code)})</option>`
        ).join('');
        if (curAdjust) adjustSelect.value = curAdjust;
      }
    }
  } catch (e) {
    console.warn('Could not populate inventory commodity dropdowns:', e);
  }
}
