/**
 * AI-Powered Smart PDS - Inventory Stock Management Controller
 * Real-time depot stock tracking, predictive replenishment, transparent procurement calculations,
 * and multi-district/commodity filtering synchronized with the executive dashboard.
 */

let inventoryAlertsData = [];
let filteredInventoryData = [];
let currentInventoryPage = 1;
const inventoryPageSize = 10;
let currentForecastLabel = 'December 2026';

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

document.addEventListener('DOMContentLoaded', async () => {
  await populateInventoryCommodityDropdowns();
  await loadInventoryData();

  // Dynamic modal pre-fill and previous-stock update on dropdown change
  const adjustCom = document.getElementById('adjust-commodity');
  const adjustReg = document.getElementById('adjust-region');
  if (adjustCom && adjustReg) {
    adjustCom.addEventListener('change', syncModalCurrentStock);
    adjustReg.addEventListener('change', syncModalCurrentStock);
  }

  // Adjust stock form submission with non-negative validation and duplicate prevention
  const adjustForm = document.getElementById('adjust-stock-form');
  if (adjustForm) {
    adjustForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const com = document.getElementById('adjust-commodity')?.value;
      const reg = document.getElementById('adjust-region')?.value;
      const rawStock = document.getElementById('adjust-new-stock')?.value || '';
      const stock = parseFloat(rawStock);

      if (rawStock.trim() === '' || isNaN(stock) || stock < 0) {
        showToast('Stock level must be a valid non-negative number (>= 0 kg).', 'error');
        return;
      }

      const submitBtn = document.getElementById('btn-save-stock') || adjustForm.querySelector('button[type="submit"]');
      const origBtnHtml = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
      }

      try {
        const res = await API.updateInventoryStock(com, reg, stock);
        if (res && res.status === 'success') {
          showToast(`Stock updated: ${com} in ${reg} set to ${stock.toLocaleString()} kg`, 'success');

          // Notify dashboard and sibling browser tabs of inventory modification
          try {
            localStorage.setItem('smart_pds_inventory_updated', Date.now().toString());
          } catch (_) {}

          closeModal('adjust-stock-modal');
          adjustForm.reset();

          // Refresh live inventory data and KPI cards
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
 * Pre-populates the modal input with current warehouse stock and updates target readout.
 */
function syncModalCurrentStock() {
  const com = document.getElementById('adjust-commodity')?.value;
  const reg = document.getElementById('adjust-region')?.value;
  const stockInput = document.getElementById('adjust-new-stock');
  const prevDisplay = document.getElementById('adjust-prev-stock-display');
  const targetLabel = document.getElementById('adjust-target-label');

  if (targetLabel && com && reg) {
    targetLabel.textContent = `${com} in ${reg}`;
  }

  if (!com || !reg) return;

  const found = inventoryAlertsData.find(item =>
    item.region && item.region.toLowerCase() === reg.toLowerCase() &&
    (item.commodity.toLowerCase() === com.toLowerCase() || item.commodity_code === com)
  );

  if (found && found.current_stock !== undefined) {
    if (prevDisplay) prevDisplay.textContent = `${Number(found.current_stock).toLocaleString()} kg`;
    if (stockInput && !stockInput.dataset.manualEdit) {
      stockInput.value = found.current_stock;
    }
  } else {
    if (prevDisplay) prevDisplay.textContent = '0 kg (New Record)';
    if (stockInput && !stockInput.dataset.manualEdit) {
      stockInput.value = '';
    }
  }
}

/**
 * Loads inventory alerts and telemetry from backend database with loading/error handling.
 */
async function loadInventoryData() {
  const tbody = document.getElementById('inventory-tbody');
  const refreshBtn = document.getElementById('btn-refresh-inv');
  if (refreshBtn) refreshBtn.disabled = true;

  if (tbody && inventoryAlertsData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;"><i class="fa-solid fa-spinner fa-spin"></i> Loading depot inventory stock &amp; ML demand telemetry...</td></tr>';
  }

  try {
    const res = await API.getInventoryAlerts();
    if (res && res.status === 'success') {
      inventoryAlertsData = res.data || [];
      if (res.forecast_label) {
        currentForecastLabel = res.forecast_label;
      } else if (res.forecast_period) {
        currentForecastLabel = res.forecast_period;
      }

      // Update forecast horizon UI tags
      const forecastTextEl = document.getElementById('forecast-period-text');
      const thForecastEl = document.getElementById('th-forecast-period');
      if (forecastTextEl) forecastTextEl.textContent = `${currentForecastLabel} (Monthly)`;
      if (thForecastEl) thForecastEl.textContent = `(${currentForecastLabel})`;

      // Re-apply filters to maintain current user view
      filterInventory();
    } else {
      showToast('Could not retrieve live inventory records.', 'error');
      if (tbody) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--accent-rose); padding:2rem;"><i class="fa-solid fa-circle-exclamation"></i> Error retrieving inventory records from database.<br><button class="btn btn-secondary btn-sm" style="margin-top:10px;" onclick="loadInventoryData()"><i class="fa-solid fa-arrows-rotate"></i> Retry</button></td></tr>';
      }
    }
  } catch (err) {
    console.error('Error fetching inventory alerts:', err);
    showToast('Failed to load inventory alerts from server.', 'error');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--accent-rose); padding:2rem;"><i class="fa-solid fa-circle-exclamation"></i> Failed to communicate with inventory API.<br><button class="btn btn-secondary btn-sm" style="margin-top:10px;" onclick="loadInventoryData()"><i class="fa-solid fa-arrows-rotate"></i> Retry</button></td></tr>';
    }
  } finally {
    if (refreshBtn) refreshBtn.disabled = false;
  }
}

/**
 * User-triggered inventory refresh
 */
async function refreshInventory() {
  await loadInventoryData();
  showToast('Inventory records and predictions refreshed', 'info');
}

/**
 * Filter change handler resetting pagination
 */
function onInventoryFilterChange() {
  currentInventoryPage = 1;
  filterInventory();
}

/**
 * Computes and renders exactly four summary KPI cards using actual MongoDB telemetry:
 * 1. Total Stock (kg)
 * 2. Shortage Locations
 * 3. Procurement Required (kg)
 * 4. Surplus Locations
 */
function updateInventoryKPIs(data, regFilter = '', comFilter = '') {
  let totalStock = 0;
  let totalProcurement = 0;
  let shortageLocations = 0;
  let surplusLocations = 0;
  let sufficientLocations = 0;

  data.forEach(item => {
    const cur = parseFloat(item.current_stock) || 0;
    const shortage = parseFloat(item.shortage) || 0;
    const proc = parseFloat(item.recommended_procurement) || 0;
    const status = (item.status || '').toUpperCase();

    totalStock += cur;
    totalProcurement += proc;

    if (shortage > 0 || status === 'SHORTAGE') {
      shortageLocations++;
    } else if (status === 'SURPLUS' || status === 'EXCESS') {
      surplusLocations++;
    } else {
      sufficientLocations++;
    }
  });

  const elTotal = document.getElementById('inv-total-stock');
  const elShortage = document.getElementById('inv-shortage-count');
  const elProcurement = document.getElementById('inv-total-procurement');
  const elSurplus = document.getElementById('inv-surplus-count');

  if (elTotal) elTotal.innerHTML = `${Math.round(totalStock).toLocaleString()} <span style="font-size:0.95rem;">kg</span>`;
  if (elShortage) elShortage.textContent = shortageLocations;
  if (elProcurement) elProcurement.innerHTML = `${Math.round(totalProcurement).toLocaleString()} <span style="font-size:0.95rem;">kg</span>`;
  if (elSurplus) elSurplus.textContent = surplusLocations;

  // Clear operational descriptions (never using misleading 'Optimal')
  const metaTotal = document.getElementById('inv-total-stock-meta');
  const metaShortage = document.getElementById('inv-shortage-meta');
  const metaProc = document.getElementById('inv-procurement-meta');
  const metaSurplus = document.getElementById('inv-surplus-meta');

  let filterLabel = 'Across all 5 districts';
  if (regFilter && comFilter) {
    filterLabel = `Filtered: ${comFilter} in ${regFilter}`;
  } else if (regFilter) {
    filterLabel = `Filtered: ${regFilter} (All Commodities)`;
  } else if (comFilter) {
    filterLabel = `Filtered: ${comFilter} (All 5 Districts)`;
  }

  if (metaTotal) metaTotal.textContent = `${filterLabel} (${data.length} depot${data.length === 1 ? '' : 's'})`;
  if (metaShortage) metaShortage.textContent = `${shortageLocations} of ${data.length} depot${data.length === 1 ? '' : 's'} below predicted demand`;
  if (metaProc) {
    metaProc.textContent = totalProcurement > 0 
      ? `Monthly replenishment needed: ${Math.round(totalProcurement).toLocaleString()} kg` 
      : 'Monthly demand fully covered (0 kg procurement needed)';
  }
  if (metaSurplus) {
    metaSurplus.textContent = `${surplusLocations} of ${data.length} depot${data.length === 1 ? '' : 's'} holding surplus stock`;
  }
}

/**
 * Filter inventory data by district and commodity in full mutual combination.
 */
function filterInventory() {
  const regSelect = document.getElementById('inv-filter-region');
  const comSelect = document.getElementById('inv-filter-commodity');
  const reg = (regSelect?.value || '').trim();
  const com = (comSelect?.value || '').trim();

  filteredInventoryData = inventoryAlertsData.filter(item => {
    const matchReg = !reg || (item.region && item.region.toLowerCase() === reg.toLowerCase());
    const matchCom = !com || 
      (item.commodity && item.commodity.toLowerCase() === com.toLowerCase()) || 
      (item.commodity_code && item.commodity_code.toUpperCase() === com.toUpperCase());
    return matchReg && matchCom;
  });

  updateInventoryKPIs(filteredInventoryData, reg, com);

  const total = filteredInventoryData.length;
  const totalPages = Math.max(1, Math.ceil(total / inventoryPageSize));
  if (currentInventoryPage > totalPages) currentInventoryPage = totalPages;

  const startIndex = (currentInventoryPage - 1) * inventoryPageSize;
  const endIndex = Math.min(startIndex + inventoryPageSize, total);
  const pageSlice = filteredInventoryData.slice(startIndex, endIndex);

  renderInventoryTable(pageSlice, reg, com);
  renderInventoryPagination(total, totalPages, startIndex, endIndex);
}

/**
 * Renders inventory table with sticky headers, readable alignments, and 3 clear statuses:
 * Shortage, Sufficient, and Surplus.
 */
function renderInventoryTable(items, regFilter = '', comFilter = '') {
  const tbody = document.getElementById('inventory-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    const filterDesc = (regFilter || comFilter) 
      ? ` for District: <strong>${escapeHtml(regFilter || 'All')}</strong>, Commodity: <strong>${escapeHtml(comFilter || 'All')}</strong>` 
      : '';
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align:center; color:var(--text-muted); padding:2.5rem;">
          <i class="fa-solid fa-box-open" style="font-size:2rem; margin-bottom:8px; display:block; opacity:0.5;"></i>
          No inventory records match filters${filterDesc}.<br>
          <button class="btn btn-secondary btn-sm" style="margin-top:10px;" onclick="clearInventoryFilters()">Clear Filters</button>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = items.map(item => {
    const curStock = parseFloat(item.current_stock) || 0;
    const hasPrediction = item.prediction_available !== false && item.predicted_demand !== null && item.predicted_demand !== undefined;
    const predDemand = hasPrediction ? parseFloat(item.predicted_demand) : null;
    
    // Difference = Current Stock - Predicted Demand
    let deltaStr = '&mdash;';
    let deltaColor = 'var(--text-muted)';
    if (predDemand !== null) {
      const delta = curStock - predDemand;
      if (item.insufficient_data && predDemand === 0) {
        deltaStr = `<span title="Difference calculated against 0 kg model output artifact. Genuine monthly demand is not zero.">+${Math.round(delta).toLocaleString()} kg*</span>`;
        deltaColor = 'var(--accent-amber)';
      } else {
        deltaStr = delta >= 0 
          ? `+${Math.round(delta).toLocaleString()} kg` 
          : `-${Math.round(Math.abs(delta)).toLocaleString()} kg`;
        deltaColor = delta >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';
      }
    }

    // Three clear statuses: Shortage, Sufficient, Surplus
    let statusBadge = '';
    const shortageQty = parseFloat(item.shortage) || (predDemand !== null && curStock < predDemand ? Math.abs(curStock - predDemand) : 0);
    const rawStatus = (item.status || '').toUpperCase();

    if (item.prediction_available === false || item.status === 'UNAVAILABLE') {
      statusBadge = '<span class="badge badge-secondary"><i class="fa-solid fa-circle-question"></i> Unavailable</span>';
    } else if (rawStatus === 'SHORTAGE' || shortageQty > 0) {
      statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> Shortage: ${Math.round(shortageQty).toLocaleString()} kg</span>`;
    } else if (rawStatus === 'SURPLUS' || rawStatus === 'EXCESS') {
      const surplusQty = predDemand !== null ? Math.round(curStock - predDemand) : 0;
      if (item.insufficient_data && predDemand === 0) {
        statusBadge = `<span class="badge badge-warning" title="${escapeHtml(item.data_quality_warning || 'Surplus calculated against zero model output')}"><i class="fa-solid fa-triangle-exclamation"></i> Surplus* (Sparse Data)</span>`;
      } else {
        statusBadge = `<span class="badge badge-info"><i class="fa-solid fa-cubes-stacked"></i> Surplus (+${surplusQty.toLocaleString()} kg)</span>`;
      }
    } else if (rawStatus === 'SUFFICIENT') {
      statusBadge = '<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> Sufficient</span>';
    } else {
      statusBadge = `<span class="badge badge-secondary">${escapeHtml(item.status || 'Active')}</span>`;
    }

    // Display demand value and alert warning if insufficient data
    let demandDisplay = '';
    if (predDemand !== null) {
      if (item.insufficient_data && predDemand === 0) {
        demandDisplay = `
          <span style="color:var(--accent-amber); font-weight:600;">0 kg/mo</span>
          <span title="${escapeHtml(item.data_quality_warning || 'Notice: Non-positive raw prediction due to sparse cardholders. Genuine monthly demand is not zero.')}" style="color:var(--accent-amber); cursor:help; margin-left:4px;">
            <i class="fa-solid fa-triangle-exclamation"></i>
          </span>
        `;
      } else if (item.insufficient_data) {
        demandDisplay = `
          <span>${Math.round(predDemand).toLocaleString()} kg/mo</span>
          <span title="${escapeHtml(item.data_quality_warning || 'Notice: High forecast uncertainty due to small demographic sample size in district')}" style="color:var(--accent-amber); cursor:help; margin-left:4px;">
            <i class="fa-solid fa-triangle-exclamation"></i>
          </span>
        `;
      } else {
        demandDisplay = `<span>${Math.round(predDemand).toLocaleString()} kg/mo</span>`;
      }
    } else {
      demandDisplay = `<span class="text-muted" title="${escapeHtml(item.data_quality_warning || item.message || 'Forecast unavailable')}"><i class="fa-solid fa-circle-question"></i> Unavailable</span>`;
    }

    // Procurement Required = max(0, Predicted Demand - Current Stock)
    const recProc = parseFloat(item.recommended_procurement) || 0;
    const procurementStr = recProc > 0
      ? `<strong style="color: var(--accent-rose);">${Math.round(recProc).toLocaleString()} kg</strong>`
      : '<span style="color: var(--text-muted);">&mdash;</span>';

    const commCode = item.commodity_code ? ` <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: normal;">(${escapeHtml(item.commodity_code)})</span>` : '';

    return `
      <tr>
        <td><strong>${escapeHtml(item.commodity)}</strong>${commCode}</td>
        <td><span class="badge badge-secondary">${escapeHtml(item.region)}</span></td>
        <td class="text-right"><strong>${Math.round(curStock).toLocaleString()} kg</strong></td>
        <td class="text-right">${demandDisplay}</td>
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
 * Renders pagination controls for inventory table
 */
function renderInventoryPagination(total, totalPages, startIndex, endIndex) {
  const infoEl = document.getElementById('inv-pagination-info');
  const controlsEl = document.getElementById('inv-pagination-controls');
  if (!infoEl || !controlsEl) return;

  if (total === 0) {
    infoEl.textContent = 'Showing 0 records';
    controlsEl.innerHTML = '';
    return;
  }

  infoEl.innerHTML = `Showing <strong>${startIndex + 1}</strong> to <strong>${endIndex}</strong> of <strong>${total}</strong> depot records`;

  if (totalPages <= 1) {
    controlsEl.innerHTML = '';
    return;
  }

  let html = `
    <button class="btn btn-secondary btn-sm" onclick="goToInventoryPage(${currentInventoryPage - 1})" ${currentInventoryPage === 1 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>
      <i class="fa-solid fa-chevron-left"></i> Prev
    </button>
  `;

  for (let i = 1; i <= totalPages; i++) {
    const isActive = i === currentInventoryPage;
    html += `
      <button class="btn ${isActive ? 'btn-primary' : 'btn-secondary'} btn-sm" style="min-width: 32px; padding: 4px 8px; font-weight: ${isActive ? '700' : '400'};" onclick="goToInventoryPage(${i})">
        ${i}
      </button>
    `;
  }

  html += `
    <button class="btn btn-secondary btn-sm" onclick="goToInventoryPage(${currentInventoryPage + 1})" ${currentInventoryPage === totalPages ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>
      Next <i class="fa-solid fa-chevron-right"></i>
    </button>
  `;

  controlsEl.innerHTML = html;
}

function goToInventoryPage(page) {
  const totalPages = Math.max(1, Math.ceil(filteredInventoryData.length / inventoryPageSize));
  if (page < 1 || page > totalPages) return;
  currentInventoryPage = page;

  const startIndex = (currentInventoryPage - 1) * inventoryPageSize;
  const endIndex = Math.min(startIndex + inventoryPageSize, filteredInventoryData.length);
  const pageSlice = filteredInventoryData.slice(startIndex, endIndex);

  const regSelect = document.getElementById('inv-filter-region');
  const comSelect = document.getElementById('inv-filter-commodity');
  renderInventoryTable(pageSlice, regSelect?.value || '', comSelect?.value || '');
  renderInventoryPagination(filteredInventoryData.length, totalPages, startIndex, endIndex);
}

function clearInventoryFilters() {
  const regSelect = document.getElementById('inv-filter-region');
  const comSelect = document.getElementById('inv-filter-commodity');
  if (regSelect) regSelect.value = '';
  if (comSelect) comSelect.value = '';
  currentInventoryPage = 1;
  filterInventory();
}

/**
 * Opens stock adjustment modal pre-populated with selected row data and previous stock readout.
 */
function openQuickAdjust(commodity, region, currentStock) {
  const comSelect = document.getElementById('adjust-commodity');
  const regSelect = document.getElementById('adjust-region');
  const stockInput = document.getElementById('adjust-new-stock');
  const prevDisplay = document.getElementById('adjust-prev-stock-display');
  const targetLabel = document.getElementById('adjust-target-label');

  if (comSelect) comSelect.value = commodity;
  if (regSelect) regSelect.value = region;
  if (targetLabel) targetLabel.textContent = `${commodity} in ${region}`;
  if (prevDisplay) prevDisplay.textContent = `${Number(currentStock).toLocaleString()} kg`;

  if (stockInput) {
    stockInput.value = currentStock;
    stockInput.dataset.manualEdit = 'true';
    setTimeout(() => {
      stockInput.focus();
      stockInput.select();
    }, 150);
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
