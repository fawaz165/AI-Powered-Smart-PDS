/**
 * AI-Powered Smart PDS - Commodity Catalog Controller
 * Handles database fetching, strict validation, unique commodity code enforcement,
 * configurable subsidized pricing, verified official NFSA vs demonstration distinctions,
 * operational linkage tracking, and safe deletion protections.
 */

let allCommodities = [];
let targetDeleteCommodityCode = null;

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadCommodities();

  // Add Commodity Form Submit Handler
  const addForm = document.getElementById('add-commodity-form');
  if (addForm) {
    addForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const code = document.getElementById('new-com-code').value.trim().toUpperCase();
      const name = document.getElementById('new-com-name').value.trim();
      const unit = document.getElementById('new-com-unit').value.trim().toLowerCase();
      const price = parseFloat(document.getElementById('new-com-price').value);
      const marketPriceVal = document.getElementById('new-com-market-price').value;
      const marketPrice = marketPriceVal !== '' ? parseFloat(marketPriceVal) : null;
      const rateType = document.getElementById('new-com-rate-type').value;
      const desc = document.getElementById('new-com-desc').value.trim();

      // Client-side Validation
      const codeRegex = /^[A-Za-z0-9\-_]{3,20}$/;
      if (!codeRegex.test(code)) {
        showToast('Commodity Code must be 3-20 alphanumeric characters (hyphens and underscores allowed).', 'error');
        return;
      }
      if (!name || name.length < 2 || name.length > 50) {
        showToast('Commodity Name must be between 2 and 50 characters.', 'error');
        return;
      }
      if (!unit) {
        showToast('Measurement unit is required.', 'error');
        return;
      }
      if (isNaN(price) || price < 0) {
        showToast('Subsidized price must be a non-negative number.', 'error');
        return;
      }
      if (marketPrice !== null && (isNaN(marketPrice) || marketPrice < 0)) {
        showToast('Market benchmark price must be a non-negative number.', 'error');
        return;
      }

      const payload = {
        commodity_code: code,
        name: name,
        unit: unit,
        subsidized_price: price,
        market_price: marketPrice,
        rate_type: rateType,
        description: desc
      };

      try {
        const res = await API.createCommodity(payload);
        if (res && res.status === 'success') {
          showToast(`Commodity ${code} (${name}) registered and persisted successfully!`, 'success');
          closeModal('add-commodity-modal');
          addForm.reset();
          await loadCommodities();
        }
      } catch (err) {
        showToast(err.message || 'Error registering commodity', 'error');
      }
    });
  }

  // Edit / Configure Commodity Form Submit Handler
  const editForm = document.getElementById('edit-commodity-form');
  if (editForm) {
    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const code = document.getElementById('edit-com-code').value.trim().toUpperCase();
      const name = document.getElementById('edit-com-name').value.trim();
      const unit = document.getElementById('edit-com-unit').value.trim().toLowerCase();
      const price = parseFloat(document.getElementById('edit-com-price').value);
      const marketPriceVal = document.getElementById('edit-com-market-price').value;
      const marketPrice = marketPriceVal !== '' ? parseFloat(marketPriceVal) : null;
      const rateType = document.getElementById('edit-com-rate-type').value;
      const desc = document.getElementById('edit-com-desc').value.trim();

      if (isNaN(price) || price < 0) {
        showToast('Subsidized price must be non-negative.', 'error');
        return;
      }
      if (marketPrice !== null && (isNaN(marketPrice) || marketPrice < 0)) {
        showToast('Market benchmark price must be non-negative.', 'error');
        return;
      }

      const payload = {
        name: name,
        unit: unit,
        subsidized_price: price,
        market_price: marketPrice,
        rate_type: rateType,
        description: desc
      };

      try {
        const res = await API.updateCommodity(code, payload);
        if (res && res.status === 'success') {
          showToast(`Commodity ${code} pricing and configuration updated successfully!`, 'success');
          closeModal('edit-commodity-modal');
          await loadCommodities();
        }
      } catch (err) {
        showToast(err.message || 'Error updating commodity', 'error');
      }
    });
  }

  // Safe Deletion Confirmation Handler
  const deleteConfirmBtn = document.getElementById('btn-confirm-delete-commodity');
  if (deleteConfirmBtn) {
    deleteConfirmBtn.addEventListener('click', async () => {
      if (!targetDeleteCommodityCode) return;
      deleteConfirmBtn.disabled = true;
      deleteConfirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking...';

      try {
        const res = await API.deleteCommodity(targetDeleteCommodityCode);
        if (res && res.status === 'success') {
          showToast(`Commodity ${targetDeleteCommodityCode} removed successfully.`, 'success');
          closeModal('delete-commodity-modal');
          targetDeleteCommodityCode = null;
          await loadCommodities();
        }
      } catch (err) {
        showToast(err.message || 'Deletion rejected by server', 'error');
      } finally {
        deleteConfirmBtn.disabled = false;
        deleteConfirmBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i> Confirm Deletion';
      }
    });
  }
});

/**
 * Loads commodity records from backend database.
 */
async function loadCommodities() {
  try {
    const res = await API.getCommodities();
    if (res && res.status === 'success') {
      allCommodities = res.data || [];
      updateCommodityKPIs(allCommodities);
      filterCommodities();
    }
  } catch (err) {
    showToast('Failed to load commodities catalog from database', 'error');
  }
}

/**
 * User-triggered catalog refresh.
 * Spins only the inner icon while the network request is active.
 */
async function refreshCommodities() {
  const btn = document.getElementById('btn-refresh-commodities');
  const icon = btn ? btn.querySelector('i') : null;
  if (btn) btn.disabled = true;
  if (icon) icon.classList.add('fa-spin');

  try {
    await loadCommodities();
    showToast('Commodity catalog refreshed from live database', 'info');
  } finally {
    if (icon) icon.classList.remove('fa-spin');
    if (btn) btn.disabled = false;
  }
}

/**
 * Computes and renders top KPI metrics cards.
 */
function updateCommodityKPIs(commodities) {
  const totalCount = commodities.length;
  let officialCount = 0;
  let demoCount = 0;
  let totalSubsidyDiscount = 0;
  let benchmarkedCount = 0;

  commodities.forEach(c => {
    if (c.rate_type === 'OFFICIAL_NFSA') {
      officialCount++;
    } else if (c.rate_type === 'DEMONSTRATION') {
      demoCount++;
    }

    if (c.market_price && c.market_price > 0) {
      const discountPct = Math.max(0, ((c.market_price - (c.subsidized_price || 0)) / c.market_price) * 100);
      totalSubsidyDiscount += discountPct;
      benchmarkedCount++;
    }
  });

  const avgSubsidyPct = benchmarkedCount > 0 ? (totalSubsidyDiscount / benchmarkedCount).toFixed(1) : '85.0';

  const elTotal = document.getElementById('com-kpi-total');
  const elOfficial = document.getElementById('com-kpi-official');
  const elDemo = document.getElementById('com-kpi-demo');
  const elDiscount = document.getElementById('com-kpi-discount');

  if (elTotal) elTotal.textContent = totalCount;
  if (elOfficial) elOfficial.textContent = officialCount;
  if (elDemo) elDemo.textContent = demoCount;
  if (elDiscount) elDiscount.innerHTML = `${avgSubsidyPct}<span style="font-size:1.1rem; font-weight:600;">%</span>`;
}

/**
 * Filters commodities based on search input and rate classification select.
 */
function filterCommodities() {
  const searchInput = document.getElementById('com-search');
  const rateFilter = document.getElementById('com-filter-rate');
  const term = searchInput ? searchInput.value.trim().toLowerCase() : '';
  const selectedType = rateFilter ? rateFilter.value : '';

  let filtered = allCommodities.filter(c => {
    const matchSearch = !term ||
      (c.commodity_code && c.commodity_code.toLowerCase().includes(term)) ||
      (c.name && c.name.toLowerCase().includes(term)) ||
      (c.description && c.description.toLowerCase().includes(term));

    const matchType = !selectedType || c.rate_type === selectedType;
    return matchSearch && matchType;
  });

  renderCommoditiesTable(filtered);
}

/**
 * Renders the commodities table rows with rate badges, benchmarks, and linkage statistics.
 */
function renderCommoditiesTable(items) {
  const tbody = document.getElementById('commodities-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">No commodities match the selected criteria.</td></tr>';
    return;
  }

  tbody.innerHTML = items.map(c => {
    const isOfficial = c.rate_type === 'OFFICIAL_NFSA';
    const isDemo = c.rate_type === 'DEMONSTRATION';

    let rateBadgeHtml = '';
    if (isOfficial) {
      rateBadgeHtml = '<span class="badge badge-success"><i class="fa-solid fa-certificate"></i> Verified Official NFSA</span>';
    } else if (isDemo) {
      rateBadgeHtml = '<span class="badge badge-warning"><i class="fa-solid fa-flask"></i> Demonstration Value</span>';
    } else {
      rateBadgeHtml = '<span class="badge badge-purple"><i class="fa-solid fa-landmark"></i> State Subsidy</span>';
    }

    // Market Benchmark & Discount Calculation
    let marketHtml = '-';
    if (c.market_price && c.market_price > 0) {
      const discountPct = Math.round(((c.market_price - (c.subsidized_price || 0)) / c.market_price) * 100);
      const discountBadge = discountPct >= 100 
        ? '<span class="badge badge-success" style="font-size:0.7rem; padding: 2px 6px;">100% Free</span>'
        : `<span class="badge badge-info" style="font-size:0.7rem; padding: 2px 6px;">-${discountPct}%</span>`;
      marketHtml = `<div style="display:flex; align-items:center; gap:6px;">
        <span>₹ ${c.market_price.toFixed(2)}</span>
        ${discountBadge}
      </div>`;
    }

    // Operational Linkages Badge
    const invCount = c.linked_inventory_count || 0;
    const txnCount = c.linked_transactions_count || 0;
    const linkageHtml = `<div style="display:flex; gap:6px; flex-wrap:wrap;">
      <span class="badge badge-info" title="Linked regional inventory stocks" style="font-size:0.72rem;">
        <i class="fa-solid fa-warehouse"></i> ${invCount} Depots
      </span>
      <span class="badge badge-purple" title="Linked distribution transactions" style="font-size:0.72rem;">
        <i class="fa-solid fa-receipt"></i> ${txnCount} Txns
      </span>
    </div>`;

    const subPriceDisplay = c.subsidized_price === 0 
      ? '<strong style="color: var(--accent-emerald);">₹ 0.00 (Free)</strong>' 
      : `<strong style="color: var(--accent-emerald);">₹ ${c.subsidized_price.toFixed(2)}</strong>`;

    return `
      <tr>
        <td><strong class="badge badge-info" style="font-family: monospace; font-size: 0.85rem; letter-spacing: 0.04em;">${escapeHtml(c.commodity_code)}</strong></td>
        <td><strong>${escapeHtml(c.name)}</strong></td>
        <td><span style="color: var(--text-secondary);">${escapeHtml(c.unit)}</span></td>
        <td>${subPriceDisplay}</td>
        <td>${marketHtml}</td>
        <td>${rateBadgeHtml}</td>
        <td>${linkageHtml}</td>
        <td>
          <div style="display: flex; gap: 6px;">
            <button class="btn btn-secondary btn-sm" title="Configure Subsidized Pricing" onclick="openConfigureCommodity('${escapeHtml(c.commodity_code)}')">
              <i class="fa-solid fa-pen-to-square"></i>
            </button>
            <button class="btn btn-secondary btn-sm" title="Delete Commodity" style="color: var(--accent-rose);" onclick="confirmDeleteCommodity('${escapeHtml(c.commodity_code)}')">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * Opens modal to configure subsidized prices, market benchmark, and classification.
 */
function openConfigureCommodity(code) {
  const commodity = allCommodities.find(c => c.commodity_code === code);
  if (!commodity) {
    showToast(`Commodity ${code} not found in catalog`, 'error');
    return;
  }

  document.getElementById('edit-com-code').value = commodity.commodity_code;
  document.getElementById('edit-com-name').value = commodity.name;
  document.getElementById('edit-com-unit').value = commodity.unit || 'kg';
  document.getElementById('edit-com-price').value = commodity.subsidized_price !== undefined ? commodity.subsidized_price : 0;
  document.getElementById('edit-com-market-price').value = commodity.market_price !== undefined ? commodity.market_price : '';
  document.getElementById('edit-com-rate-type').value = commodity.rate_type || 'OFFICIAL_NFSA';
  document.getElementById('edit-com-desc').value = commodity.description || '';

  openModal('edit-commodity-modal');
}

/**
 * Opens safe deletion confirmation dialog with linkage audit checks.
 */
function confirmDeleteCommodity(code) {
  const commodity = allCommodities.find(c => c.commodity_code === code);
  if (!commodity) return;

  targetDeleteCommodityCode = code;
  const nameElem = document.getElementById('delete-com-target-name');
  const detailsElem = document.getElementById('delete-com-linkage-warning');
  const confirmBtn = document.getElementById('btn-confirm-delete-commodity');

  if (nameElem) {
    nameElem.textContent = `${commodity.commodity_code} (${commodity.name})`;
  }

  const invCount = commodity.linked_inventory_count || 0;
  const txnCount = commodity.linked_transactions_count || 0;

  if (invCount > 0 || txnCount > 0) {
    if (detailsElem) {
      detailsElem.style.display = 'block';
      detailsElem.innerHTML = `
        <div style="background: rgba(244, 63, 94, 0.12); border: 1px solid rgba(244, 63, 94, 0.35); border-radius: var(--radius-sm); padding: 12px; margin-top: 10px;">
          <p style="color: #fda4af; font-weight: 600; margin-bottom: 4px;">
            <i class="fa-solid fa-triangle-exclamation"></i> Operational Linkage Detected
          </p>
          <p style="color: var(--text-secondary); font-size: 0.84rem;">
            This commodity is currently linked to <strong>${invCount} regional depot stock record(s)</strong> and <strong>${txnCount} distribution transaction(s)</strong>.
            Deleting it will corrupt inventory audits and is blocked by the backend to maintain operational integrity.
          </p>
        </div>
      `;
    }
  } else {
    if (detailsElem) {
      detailsElem.style.display = 'none';
      detailsElem.innerHTML = '';
    }
  }

  openModal('delete-commodity-modal');
}
