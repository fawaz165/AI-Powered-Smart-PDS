/**
 * AI-Powered Smart PDS - Commodity Catalog Controller
 * Handles database fetching, strict validation, unique commodity code enforcement,
 * configurable subsidized pricing, verified official NFSA vs synthetic demonstration distinctions,
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

      // Client-side Strict Validation
      const codeRegex = /^[A-Za-z0-9\-_]{3,20}$/;
      if (!codeRegex.test(code)) {
        showToast('Commodity Code must be 3-20 alphanumeric characters (hyphens and underscores allowed).', 'error');
        return;
      }
      const nameRegex = /^[A-Za-z][A-Za-z0-9\s\-_()]{1,49}$/;
      if (!nameRegex.test(name)) {
        showToast('Commodity Name must start with a letter and be 2-50 characters long.', 'error');
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
      if (marketPrice !== null) {
        if (isNaN(marketPrice) || marketPrice < 0) {
          showToast('Market benchmark price must be a non-negative number.', 'error');
          return;
        }
        if (marketPrice < price) {
          showToast(`Market benchmark price (₹${marketPrice.toFixed(2)}) cannot be lower than subsidized price (₹${price.toFixed(2)}).`, 'error');
          return;
        }
      }

      // Legal statutory check: Never label unverified rates (> ₹15.0/kg) as Official NFSA
      if (rateType === 'OFFICIAL_NFSA' && price > 15.0) {
        showToast("Unverified price (> ₹15.00/kg) cannot be labeled as Official NFSA. Statutory NFSA cap is ₹13.50/kg for sugar and ₹3.00/kg for grains. Choose 'Synthetic Demo Rate' or 'State Welfare Subsidy'.", 'error');
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

      const nameRegex = /^[A-Za-z][A-Za-z0-9\s\-_()]{1,49}$/;
      if (!nameRegex.test(name)) {
        showToast('Commodity Name must start with a letter and be 2-50 characters long.', 'error');
        return;
      }
      if (isNaN(price) || price < 0) {
        showToast('Subsidized price must be non-negative.', 'error');
        return;
      }
      if (marketPrice !== null) {
        if (isNaN(marketPrice) || marketPrice < 0) {
          showToast('Market benchmark price must be non-negative.', 'error');
          return;
        }
        if (marketPrice < price) {
          showToast(`Market benchmark price (₹${marketPrice.toFixed(2)}) cannot be lower than subsidized price (₹${price.toFixed(2)}).`, 'error');
          return;
        }
      }

      // Legal statutory check: Never label unverified rates (> ₹15.0/kg) as Official NFSA
      if (rateType === 'OFFICIAL_NFSA' && price > 15.0) {
        showToast("Unverified price (> ₹15.00/kg) cannot be labeled as Official NFSA. Statutory NFSA cap is ₹13.50/kg for sugar and ₹3.00/kg for grains. Choose 'Synthetic Demo Rate' or 'State Welfare Subsidy'.", 'error');
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
 * Displays full loading state in the table body.
 */
function setCommoditiesLoadingState() {
  const tbody = document.getElementById('commodities-tbody');
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 3rem 1.5rem;">
          <i class="fa-solid fa-circle-notch fa-spin" style="font-size: 1.8rem; color: var(--primary); margin-bottom: 12px; display: block;"></i>
          <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 4px;">Loading food-grain catalog...</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">Connecting to MongoDB cluster and aggregating operational linkages</div>
        </td>
      </tr>
    `;
  }
}

/**
 * Displays error state with retry button in the table body.
 */
function setCommoditiesErrorState(errorMessage) {
  const tbody = document.getElementById('commodities-tbody');
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--accent-rose); padding: 3rem 1.5rem;">
          <i class="fa-solid fa-triangle-exclamation" style="font-size: 2rem; margin-bottom: 12px; display: block;"></i>
          <div style="font-weight: 700; font-size: 1rem; margin-bottom: 6px;">Failed to Load Commodity Catalog</div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); max-width: 500px; margin: 0 auto 16px auto;">
            ${escapeHtml(errorMessage || 'Unable to retrieve commodity master records from MongoDB database.')}
          </div>
          <button class="btn btn-primary btn-sm" onclick="loadCommodities()" style="padding: 8px 18px;">
            <i class="fa-solid fa-arrows-rotate"></i> Retry Connection
          </button>
        </td>
      </tr>
    `;
  }
  // Keep KPI cards safely in fallback state
  const elTotal = document.getElementById('com-kpi-total');
  const elOfficial = document.getElementById('com-kpi-official');
  const elDemo = document.getElementById('com-kpi-demo');
  const elDiscount = document.getElementById('com-kpi-discount');
  if (elTotal) elTotal.textContent = '--';
  if (elOfficial) elOfficial.textContent = '--';
  if (elDemo) elDemo.textContent = '--';
  if (elDiscount) elDiscount.innerHTML = `--<span style="font-size:1.1rem; font-weight:600;">%</span>`;
}

/**
 * Displays empty state for zero commodities or no filter match.
 */
function setCommoditiesEmptyState(isSearchOrFilter = false) {
  const tbody = document.getElementById('commodities-tbody');
  if (!tbody) return;
  if (isSearchOrFilter) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2.5rem 1.5rem;">
          <i class="fa-solid fa-magnifying-glass" style="font-size: 1.8rem; color: var(--text-muted); margin-bottom: 10px; display: block;"></i>
          <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 4px;">No Matching Commodities Found</div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 12px;">Try adjusting your keyword search or rate classification filter.</div>
          <button class="btn btn-secondary btn-sm" onclick="resetCommodityFilters()">
            <i class="fa-solid fa-filter-circle-xmark"></i> Reset Filters
          </button>
        </td>
      </tr>
    `;
  } else {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2.5rem 1.5rem;">
          <i class="fa-solid fa-boxes-stacked" style="font-size: 2rem; color: var(--text-muted); margin-bottom: 10px; display: block;"></i>
          <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 4px;">No Commodities Registered in Database</div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 14px;">The central catalog has no active records. Click below to add your first commodity.</div>
          <button class="btn btn-primary btn-sm" onclick="openModal('add-commodity-modal')">
            <i class="fa-solid fa-plus"></i> Add First Commodity
          </button>
        </td>
      </tr>
    `;
  }
}

/**
 * Loads commodity records from backend database.
 */
async function loadCommodities() {
  setCommoditiesLoadingState();
  try {
    const res = await API.getCommodities({ timeout: 10000 });
    if (res && res.status === 'success') {
      allCommodities = res.data || [];
      updateCommodityKPIs(allCommodities, res.summary);
      if (allCommodities.length === 0) {
        setCommoditiesEmptyState(false);
      } else {
        filterCommodities();
      }
    } else {
      setCommoditiesErrorState(res ? res.message : 'Invalid response from database');
    }
  } catch (err) {
    console.error('Failed to load commodities catalog:', err);
    setCommoditiesErrorState(err.message || 'Network error connecting to MongoDB backend');
    showToast(err.message || 'Failed to load commodities catalog from database', 'error');
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
 * Computes and renders top KPI metrics cards dynamically from database records.
 * Uses a clearly defined unweighted arithmetic mean across valid benchmarked commodities.
 * Excludes invalid or negative records. No hardcoded replacement statistics.
 */
function updateCommodityKPIs(commodities, summary) {
  let totalCount = commodities.length;
  let officialCount = 0;
  let demoCount = 0;
  let totalSubsidyDiscount = 0;
  let benchmarkedCount = 0;

  commodities.forEach(c => {
    // Verified official schemes include statutory NFSA and Tamil Nadu State Welfare Subsidies (e.g. Special PDS)
    const isOfficialVerified = Boolean(
      (c.rate_type === 'OFFICIAL_NFSA' || c.rate_type === 'STATE_SUBSIDY') &&
      c.is_verified &&
      !c.is_demonstration
    );
    if (isOfficialVerified) {
      officialCount++;
    } else {
      demoCount++;
    }

    const mkt = Number(c.market_price);
    const sub = Number(c.subsidized_price);
    // Strictly validate: positive market price, non-negative subsidized price, and market >= subsidized
    if (!isNaN(mkt) && mkt > 0 && !isNaN(sub) && sub >= 0 && mkt >= sub) {
      const discountPct = (c.subsidy_percentage !== undefined && c.subsidy_percentage !== null)
        ? Number(c.subsidy_percentage)
        : Math.max(0, Math.min(100, ((mkt - sub) / mkt) * 100));
      totalSubsidyDiscount += discountPct;
      benchmarkedCount++;
    }
  });

  // Calculate dynamic arithmetic mean across valid benchmarked commodities
  const avgSubsidyPct = (summary && summary.average_subsidy_discount !== undefined)
    ? Number(summary.average_subsidy_discount).toFixed(1)
    : (benchmarkedCount > 0 ? (totalSubsidyDiscount / benchmarkedCount).toFixed(1) : '0.0');

  const elTotal = document.getElementById('com-kpi-total');
  const elOfficial = document.getElementById('com-kpi-official');
  const elDemo = document.getElementById('com-kpi-demo');
  const elDiscount = document.getElementById('com-kpi-discount');

  if (elTotal) elTotal.textContent = (summary && summary.total_count !== undefined) ? summary.total_count : totalCount;
  if (elOfficial) elOfficial.textContent = (summary && summary.official_count !== undefined) ? summary.official_count : officialCount;
  if (elDemo) elDemo.textContent = (summary && summary.demo_count !== undefined) ? summary.demo_count : demoCount;
  if (elDiscount) elDiscount.innerHTML = `${avgSubsidyPct}<span style="font-size:1.1rem; font-weight:600;">%</span>`;
}

/**
 * Resets search and filter inputs and triggers refresh.
 */
function resetCommodityFilters() {
  const searchInput = document.getElementById('com-search');
  const rateFilter = document.getElementById('com-filter-rate');
  if (searchInput) searchInput.value = '';
  if (rateFilter) rateFilter.value = '';
  filterCommodities();
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
      (c.description && c.description.toLowerCase().includes(term)) ||
      (c.official_source && c.official_source.toLowerCase().includes(term));

    let matchType = true;
    if (selectedType === 'OFFICIAL_NFSA') {
      matchType = Boolean(c.rate_type === 'OFFICIAL_NFSA' && c.is_verified && !c.is_demonstration);
    } else if (selectedType === 'DEMONSTRATION') {
      matchType = Boolean(c.rate_type === 'DEMONSTRATION' || c.is_demonstration || !c.is_verified);
    } else if (selectedType === 'STATE_SUBSIDY') {
      matchType = Boolean(c.rate_type === 'STATE_SUBSIDY');
    }

    return matchSearch && matchType;
  });

  if (filtered.length === 0) {
    setCommoditiesEmptyState(allCommodities.length > 0);
  } else {
    renderCommoditiesTable(filtered);
  }
}

/**
 * Renders the commodities table rows with rate badges, benchmarks, and linkage statistics.
 */
function renderCommoditiesTable(items) {
  const tbody = document.getElementById('commodities-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    setCommoditiesEmptyState(true);
    return;
  }

  tbody.innerHTML = items.map(c => {
    const isOfficial = Boolean(c.rate_type === 'OFFICIAL_NFSA' && c.is_verified && !c.is_demonstration);
    const isStateSubsidy = Boolean(c.rate_type === 'STATE_SUBSIDY');

    let rateBadgeHtml = '';
    if (c.commodity_code === 'COM-DAL' || isStateSubsidy) {
      rateBadgeHtml = '<span class="badge badge-purple" title="Tamil Nadu Special Public Distribution System (Special PDS Scheme)"><i class="fa-solid fa-landmark"></i> Tamil Nadu Special PDS</span>';
    } else if (isOfficial) {
      rateBadgeHtml = '<span class="badge badge-success" title="Verified statutory NFSA / State Universal PDS entitlement"><i class="fa-solid fa-certificate"></i> Verified Official NFSA</span>';
    } else {
      rateBadgeHtml = '<span class="badge badge-warning" title="Synthetic simulation value - Not statutory official rate"><i class="fa-solid fa-flask"></i> Synthetic Demo Rate</span>';
    }

    const unitStr = escapeHtml(c.unit || 'kg');
    const subPriceVal = Number(c.subsidized_price || 0);

    // Subsidized Price Display (Supports Category-Based Sugar Pricing & Free Entitlements)
    let subPriceDisplay = '';
    if (c.commodity_code === 'COM-SUG' || c.category_pricing) {
      const cp = c.category_pricing || { AAY: 13.50, PHH: 25.00, NPHH: 25.00 };
      subPriceDisplay = `
        <div style="display:flex; flex-direction:column; gap:2px;">
          <div><span class="badge badge-purple" style="font-size:0.65rem; padding:1px 4px;">AAY</span> <strong style="color:var(--accent-emerald);">₹ ${Number(cp.AAY || 13.50).toFixed(2)} / ${unitStr}</strong></div>
          <div style="font-size:0.75rem; color:var(--text-secondary);"><span class="badge badge-info" style="font-size:0.65rem; padding:1px 4px;">PHH/NPHH</span> ₹ ${Number(cp.PHH || 25.00).toFixed(2)} / ${unitStr}</div>
        </div>
      `;
    } else if (subPriceVal === 0) {
      subPriceDisplay = `<strong style="color: var(--accent-emerald);">₹ 0.00 / ${unitStr}</strong> <span class="badge badge-success" style="font-size:0.7rem; padding: 1px 5px;">Free Entitlement</span>`;
    } else {
      subPriceDisplay = `<strong style="color: var(--accent-emerald);">₹ ${subPriceVal.toFixed(2)} / ${unitStr}</strong>`;
    }

    // Reference Open Market Benchmark & Subsidy Calculation Display
    let marketHtml = '<span style="color: var(--text-muted);">-</span>';
    if (c.market_price && c.market_price > 0) {
      const mktPriceVal = Number(c.market_price);
      const diffAmount = (c.subsidy_amount !== undefined && c.subsidy_amount !== null)
        ? Number(c.subsidy_amount)
        : Math.max(0, mktPriceVal - subPriceVal);
      const discountPct = (c.subsidy_percentage !== undefined && c.subsidy_percentage !== null)
        ? Math.round(Number(c.subsidy_percentage))
        : Math.round((diffAmount / mktPriceVal) * 100);
      const savingsBadge = discountPct >= 100 
        ? '<span class="badge badge-success" style="font-size:0.7rem; padding: 2px 6px;">100% Free Entitlement</span>'
        : `<span class="badge badge-info" style="font-size:0.7rem; padding: 2px 6px;">Save ₹${diffAmount.toFixed(2)} (-${discountPct}%)</span>`;
      marketHtml = `
        <div style="display:flex; flex-direction:column; gap:2px;">
          <span style="font-weight: 500;">₹ ${mktPriceVal.toFixed(2)} / ${unitStr}</span>
          <span style="font-size:0.68rem; color:var(--text-muted);">Ref. Open Market Benchmark</span>
          <div>${savingsBadge}</div>
        </div>
      `;
    }

    // Official Scheme Source Subtitle
    const sourceHtml = c.official_source 
      ? `<div style="font-size:0.7rem; color:var(--text-muted); margin-top:3px;"><i class="fa-solid fa-shield-halved" style="color:var(--accent-cyan); font-size:0.65rem;"></i> ${escapeHtml(c.official_source)}</div>`
      : '';

    // Operational Linkages Badges
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

    return `
      <tr>
        <td><code>${escapeHtml(c.commodity_code)}</code></td>
        <td>
          <strong style="color:var(--text-primary);">${escapeHtml(c.name)}</strong>
          ${sourceHtml}
        </td>
        <td>${unitStr}</td>
        <td>${subPriceDisplay}</td>
        <td>${marketHtml}</td>
        <td>${rateBadgeHtml}</td>
        <td>${linkageHtml}</td>
        <td>
          <div style="display:flex; gap:6px; align-items:center;">
            <button class="btn btn-secondary btn-sm" onclick="openConfigureCommodity('${escapeHtml(c.commodity_code)}')" title="Configure Subsidized Pricing">
              <i class="fa-solid fa-sliders"></i>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="confirmDeleteCommodity('${escapeHtml(c.commodity_code)}')" title="Delete Commodity" style="color:var(--accent-rose);">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// Aliases for compatibility
function openEditCommodityModal(code) {
  openConfigureCommodity(code);
}

function promptDeleteCommodity(code) {
  confirmDeleteCommodity(code);
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
