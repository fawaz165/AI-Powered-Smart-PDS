/**
 * AI-Powered Smart PDS - Beneficiaries Registry Controller
 * Handles NFSA entitlement calculations, CRUD operations (Add, Edit, Safe Delete),
 * real-time search & regional filtering, pagination, and live database metric synchronization.
 */

let allBeneficiaries = [];
let filteredBeneficiaries = [];
let targetDeleteBeneficiaryId = null;
let configuredEntitlementRules = null;
let currentPage = 1;
const pageSize = 8;

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadEntitlementRules();
  await fetchBeneficiaries(true);
  updateEntitlementPreview();

  // 1. Form submission for registering new beneficiary
  const addForm = document.getElementById('add-beneficiary-form');
  if (addForm) {
    addForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const bid = document.getElementById('new-ben-id').value.trim().toUpperCase();
      const name = document.getElementById('new-ben-name').value.trim();
      const region = document.getElementById('new-ben-region').value;
      const size = parseInt(document.getElementById('new-ben-size').value, 10);
      const type = document.getElementById('new-ben-type').value;
      const cardNumInput = document.getElementById('new-ben-card-num');
      const cardNum = cardNumInput ? cardNumInput.value.trim().toUpperCase() : '';

      // Client-side validation: Beneficiary ID
      if (!bid || bid.length < 3) {
        showToast('Beneficiary ID must be at least 3 characters.', 'error');
        return;
      }
      if (allBeneficiaries.some(b => b.beneficiary_id && b.beneficiary_id.toUpperCase() === bid)) {
        showToast(`Beneficiary ID '${bid}' is already registered in the database.`, 'error');
        return;
      }

      // Client-side validation: Name
      if (!name || name.length < 2) {
        showToast('Full name must be at least 2 characters.', 'error');
        return;
      }

      // Client-side validation: Family Size (1 - 25)
      if (isNaN(size) || size < 1 || size > 25) {
        showToast('Family size must be a valid integer between 1 and 25.', 'error');
        return;
      }

      // Client-side validation: Ration Card Number
      if (cardNum && allBeneficiaries.some(b => b.ration_card_number && b.ration_card_number.toUpperCase() === cardNum)) {
        showToast(`Ration Card Number '${cardNum}' is already assigned to another cardholder.`, 'error');
        return;
      }

      const payload = {
        beneficiary_id: bid,
        name: name,
        region: region,
        family_size: size,
        ration_card_type: type
      };
      if (cardNum) {
        payload.ration_card_number = cardNum;
      }

      try {
        const res = await API.createBeneficiary(payload);
        if (res && res.status === 'success') {
          showToast(`Beneficiary ${bid} registered and persisted successfully!`, 'success');
          closeModal('add-beneficiary-modal');
          addForm.reset();
          await fetchBeneficiaries(false);
          try { localStorage.setItem('smart_pds_beneficiary_updated', Date.now().toString()); } catch (_) {}
        }
      } catch (err) {
        showToast(err.message || 'Error registering beneficiary', 'error');
      }
    });
  }

  // 2. Form submission for editing existing beneficiary
  const editForm = document.getElementById('edit-beneficiary-form');
  if (editForm) {
    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const bid = document.getElementById('edit-ben-id').value.trim().toUpperCase();
      const name = document.getElementById('edit-ben-name').value.trim();
      const region = document.getElementById('edit-ben-region').value;
      const size = parseInt(document.getElementById('edit-ben-size').value, 10);
      const type = document.getElementById('edit-ben-type').value;
      const cardNum = document.getElementById('edit-ben-card-num').value.trim().toUpperCase();

      if (!name || name.length < 2) {
        showToast('Full name must be at least 2 characters.', 'error');
        return;
      }
      if (isNaN(size) || size < 1 || size > 25) {
        showToast('Family size must be an integer between 1 and 25.', 'error');
        return;
      }
      if (!cardNum || cardNum.length < 3) {
        showToast('Ration Card Number must be at least 3 characters.', 'error');
        return;
      }

      // Check card number conflict against other beneficiaries
      const conflict = allBeneficiaries.find(b => 
        b.ration_card_number && 
        b.ration_card_number.toUpperCase() === cardNum && 
        b.beneficiary_id.toUpperCase() !== bid
      );
      if (conflict) {
        showToast(`Ration Card Number '${cardNum}' is already assigned to beneficiary ${conflict.beneficiary_id}.`, 'error');
        return;
      }

      const payload = {
        name: name,
        region: region,
        family_size: size,
        ration_card_type: type,
        ration_card_number: cardNum
      };

      const saveBtn = document.getElementById('btn-save-edit-ben');
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
      }

      try {
        const res = await API.updateBeneficiary(bid, payload);
        if (res && res.status === 'success') {
          showToast(`Cardholder ${bid} updated successfully!`, 'success');
          closeModal('edit-beneficiary-modal');
          await fetchBeneficiaries(false);
          try { localStorage.setItem('smart_pds_beneficiary_updated', Date.now().toString()); } catch (_) {}
        }
      } catch (err) {
        showToast(err.message || 'Error updating cardholder', 'error');
      } finally {
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save Changes';
        }
      }
    });
  }
});

/**
 * Loads configured entitlement rules from backend to avoid hardcoded calculations.
 */
async function loadEntitlementRules() {
  try {
    const res = await API.request('/beneficiaries/rules');
    if (res && res.status === 'success') {
      configuredEntitlementRules = res.data;
    }
  } catch (err) {
    console.warn('Could not load remote entitlement rules, using local NFSA standards:', err);
  }
}

/**
 * Robustly normalizes raw ration card type string into canonical category ('PHH', 'AAY', 'NPHH').
 * Accounts for case differences, leading/trailing whitespace, punctuation, and substring permutations.
 * Checks NPHH first to prevent false substring collision with 'Priority' / 'PHH'.
 */
function normalizeRationCardType(rawType) {
  const s = String(rawType || '').trim().toUpperCase();
  if (s.includes('NPHH') || s.includes('NON-PRIORITY') || s.includes('NON PRIORITY') || s.includes('NON_PRIORITY')) {
    return 'NPHH';
  }
  if (s.includes('AAY') || s.includes('ANTYODAYA') || s.includes('ANNA YOJANA')) {
    return 'AAY';
  }
  if (s.includes('PHH') || s.includes('PRIORITY')) {
    return 'PHH';
  }
  return 'PHH';
}

/**
 * Computes statutory NFSA foodgrain entitlements and separate State-scheme allocations:
 * - PHH: Statutory NFSA = Family size × 5 kg foodgrains per person per month.
 *        Additional state allocations: Wheat (2 kg/person), Sugar (1 kg), Dal (1 kg).
 * - AAY: Statutory NFSA = 35 kg foodgrains per household per month (Fixed).
 *        Additional state allocations: Sugar (2 kg), Dal (2 kg).
 * - NPHH: Non-NFSA (no statutory central quota asserted).
 *         State-scheme: Displays active state allocation, or "State scheme – not configured" if none exists.
 * Guarantees: Never displays 0 kg when valid entitlement data exists.
 */
function computeMonthlyQuota(cardType, size, existingQuota = null, existingEntitlement = null) {
  const s = Math.max(1, parseInt(size, 10) || 1);
  const category = normalizeRationCardType(cardType);

  let nfsaKg = null;
  let nfsaBadgeHtml = '';
  let nfsaFormulaText = '';
  let stateAllocationsList = [];
  let stateAllocationsText = '';

  if (category === 'PHH') {
    nfsaKg = s * 5;
    nfsaBadgeHtml = `<span class="badge badge-nfsa"><i class="fa-solid fa-wheat-awn"></i> NFSA: ${nfsaKg} kg/mo</span>`;
    nfsaFormulaText = `(${s} member${s > 1 ? 's' : ''} &times; 5 kg/person)`;

    if (existingEntitlement && existingEntitlement.state_allocations_text) {
      stateAllocationsText = existingEntitlement.state_allocations_text;
    } else {
      let quota = (existingQuota && typeof existingQuota === 'object' && Object.keys(existingQuota).length > 0)
        ? { ...existingQuota }
        : { Rice: s * 5.0, Wheat: s * 2.0, Sugar: 1.0, Dal: 1.0 };

      Object.entries(quota).forEach(([comm, val]) => {
        if (comm !== 'Rice' && comm !== 'Foodgrains' && Number(val) > 0) {
          const num = Number(val);
          stateAllocationsList.push(`${escapeHtml(comm)} ${Number.isInteger(num) ? num : num.toFixed(1)}kg`);
        }
      });
      stateAllocationsText = stateAllocationsList.length > 0
        ? stateAllocationsList.join(', ')
        : 'None configured';
    }

  } else if (category === 'AAY') {
    nfsaKg = 35;
    nfsaBadgeHtml = `<span class="badge badge-nfsa-aay"><i class="fa-solid fa-wheat-awn"></i> NFSA: 35 kg/mo</span>`;
    nfsaFormulaText = `(Fixed 35 kg/household)`;

    if (existingEntitlement && existingEntitlement.state_allocations_text) {
      stateAllocationsText = existingEntitlement.state_allocations_text;
    } else {
      let quota = (existingQuota && typeof existingQuota === 'object' && Object.keys(existingQuota).length > 0)
        ? { ...existingQuota }
        : { Rice: 25.0, Wheat: 10.0, Sugar: 2.0, Dal: 2.0 };

      Object.entries(quota).forEach(([comm, val]) => {
        if (comm !== 'Rice' && comm !== 'Wheat' && comm !== 'Foodgrains' && Number(val) > 0) {
          const num = Number(val);
          stateAllocationsList.push(`${escapeHtml(comm)} ${Number.isInteger(num) ? num : num.toFixed(1)}kg`);
        }
      });
      stateAllocationsText = stateAllocationsList.length > 0
        ? stateAllocationsList.join(', ')
        : 'None configured';
    }

  } else { // NPHH
    nfsaKg = null;
    nfsaBadgeHtml = `<span class="badge badge-non-nfsa"><i class="fa-solid fa-circle-minus"></i> Non-NFSA</span>`;
    nfsaFormulaText = `(No statutory central quota)`;

    if (existingEntitlement && existingEntitlement.state_allocations_text) {
      stateAllocationsText = existingEntitlement.state_allocations_text;
    } else {
      let quota = (existingQuota && typeof existingQuota === 'object' && Object.keys(existingQuota).length > 0)
        ? { ...existingQuota }
        : { Rice: Number((s * 3.0).toFixed(1)), Wheat: Number((s * 1.5).toFixed(1)), Sugar: 1.0, Dal: 0.5 };

      const hasActualAllocation = Object.values(quota).some(v => Number(v) > 0);
      if (hasActualAllocation) {
        Object.entries(quota).forEach(([comm, val]) => {
          if (Number(val) > 0) {
            const num = Number(val);
            stateAllocationsList.push(`${escapeHtml(comm)} ${Number.isInteger(num) ? num : num.toFixed(1)}kg`);
          }
        });
        stateAllocationsText = stateAllocationsList.length > 0
          ? stateAllocationsList.join(', ')
          : 'State scheme – not configured';
      } else {
        stateAllocationsText = 'State scheme – not configured';
      }
    }
  }

  // HTML for directory table cell (compact, responsive, clearly separated)
  const isNphhNotConfigured = category === 'NPHH' && stateAllocationsText.includes('not configured');
  const tableHtml = `
    <div class="entitlement-cell-content">
      <div class="nfsa-entitlement-row">
        ${nfsaBadgeHtml}
        <span class="entitlement-formula">${nfsaFormulaText}</span>
      </div>
      <div class="state-scheme-row">
        <span class="state-label">State/Demo:</span>
        <span class="state-commodities ${isNphhNotConfigured ? 'text-muted' : ''}">${stateAllocationsText}</span>
      </div>
    </div>
  `;

  // HTML for modal previews (Add / Edit modals)
  let previewHtml = '';
  if (category === 'PHH') {
    previewHtml = `
      <div style="display:flex; flex-direction:column; gap:5px;">
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <span class="badge badge-nfsa"><i class="fa-solid fa-wheat-awn"></i> Statutory NFSA: ${nfsaKg} kg/month</span>
          <span style="color:var(--text-muted); font-size:0.78rem;">(${s} member${s > 1 ? 's' : ''} &times; 5 kg/person/month)</span>
        </div>
        <div style="font-size:0.8rem; color:var(--text-secondary); line-height:1.4;">
          <strong style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; letter-spacing:0.03em;">Additional State Welfare:</strong>
          <span style="color:var(--text-primary); margin-left:4px;">${stateAllocationsText}</span>
        </div>
      </div>
    `;
  } else if (category === 'AAY') {
    previewHtml = `
      <div style="display:flex; flex-direction:column; gap:5px;">
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <span class="badge badge-nfsa-aay"><i class="fa-solid fa-wheat-awn"></i> Statutory NFSA: 35 kg/month</span>
          <span style="color:var(--text-muted); font-size:0.78rem;">(Fixed 35 kg/household/month)</span>
        </div>
        <div style="font-size:0.8rem; color:var(--text-secondary); line-height:1.4;">
          <strong style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; letter-spacing:0.03em;">Additional State Welfare:</strong>
          <span style="color:var(--text-primary); margin-left:4px;">${stateAllocationsText}</span>
        </div>
      </div>
    `;
  } else {
    previewHtml = `
      <div style="display:flex; flex-direction:column; gap:5px;">
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <span class="badge badge-non-nfsa"><i class="fa-solid fa-circle-minus"></i> Non-NFSA</span>
          <span style="color:var(--text-muted); font-size:0.78rem;">(Non-Priority Household &bull; No statutory central quota)</span>
        </div>
        <div style="font-size:0.8rem; color:var(--text-secondary); line-height:1.4;">
          <strong style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; letter-spacing:0.03em;">State Scheme Allocation:</strong>
          <span style="color:${isNphhNotConfigured ? 'var(--text-muted)' : 'var(--text-primary)'}; margin-left:4px;">${stateAllocationsText}</span>
        </div>
      </div>
    `;
  }

  return {
    category,
    size: s,
    nfsaKg,
    quota: existingQuota,
    stateAllocationsText,
    tableHtml,
    previewHtml,
    html: previewHtml
  };
}

/**
 * Updates live preview for Add Beneficiary modal
 */
function updateEntitlementPreview() {
  const previewEl = document.getElementById('entitlement-preview');
  if (!previewEl) return;

  const size = parseInt(document.getElementById('new-ben-size')?.value || '4', 10);
  const cardType = document.getElementById('new-ben-type')?.value || 'Priority (PHH)';
  const res = computeMonthlyQuota(cardType, size);
  previewEl.innerHTML = res.previewHtml;
}

/**
 * Updates live preview for Edit Beneficiary modal
 */
function updateEditEntitlementPreview() {
  const previewEl = document.getElementById('edit-entitlement-preview');
  if (!previewEl) return;

  const size = parseInt(document.getElementById('edit-ben-size')?.value || '4', 10);
  const cardType = document.getElementById('edit-ben-type')?.value || 'Priority (PHH)';
  const res = computeMonthlyQuota(cardType, size);
  previewEl.innerHTML = res.previewHtml;
}

/**
 * Fetches all beneficiaries from live backend API.
 */
async function fetchBeneficiaries(isInitial = false) {
  const tbody = document.getElementById('beneficiaries-tbody');
  if (tbody && isInitial) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding: 1.5rem;"><i class="fa-solid fa-spinner fa-spin"></i> Loading cardholders from database...</td></tr>';
  }

  try {
    const res = await API.getBeneficiaries({ limit: 0 });
    if (res && res.status === 'success') {
      allBeneficiaries = res.data || [];
      updateRegistryMetrics(allBeneficiaries, res.summary || res.categories);
      applyFilteringAndPagination();
    }
  } catch (err) {
    console.error('Failed to load beneficiaries:', err);
    showToast('Failed to load beneficiaries from database', 'error');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--accent-rose); padding: 1.5rem;"><i class="fa-solid fa-circle-exclamation"></i> Error loading registry data. Please retry.</td></tr>';
    }
  }
}

/**
 * Updates summary metric KPI counters dynamically from database records.
 */
function updateRegistryMetrics(beneficiaries, categorySummary = null) {
  let total = Array.isArray(beneficiaries) ? beneficiaries.length : 0;
  let phhCount = 0;
  let aayCount = 0;
  let nphhCount = 0;

  const categories = categorySummary?.categories || categorySummary;
  if (categories && typeof categories === 'object' && ('PHH' in categories || 'AAY' in categories || 'NPHH' in categories)) {
    phhCount = Number(categories.PHH) || 0;
    aayCount = Number(categories.AAY) || 0;
    nphhCount = Number(categories.NPHH) || 0;
    total = Number(categorySummary?.total ?? (phhCount + aayCount + nphhCount));
  } else if (Array.isArray(beneficiaries)) {
    beneficiaries.forEach(b => {
      const cat = normalizeRationCardType(b.ration_card_type);
      if (cat === 'NPHH') {
        nphhCount++;
      } else if (cat === 'AAY') {
        aayCount++;
      } else {
        phhCount++;
      }
    });
    total = beneficiaries.length;
  }

  const totalEl = document.getElementById('ben-kpi-total');
  const phhEl = document.getElementById('ben-kpi-phh');
  const aayEl = document.getElementById('ben-kpi-aay');
  const nphhEl = document.getElementById('ben-kpi-nphh');

  if (totalEl) totalEl.textContent = total;
  if (phhEl) phhEl.textContent = phhCount;
  if (aayEl) aayEl.textContent = aayCount;
  if (nphhEl) nphhEl.textContent = nphhCount;
}

/**
 * User-triggered registry table refresh.
 */
async function refreshBeneficiaries() {
  const btn = document.getElementById('btn-refresh-bens');
  if (btn) btn.disabled = true;
  await fetchBeneficiaries(false);
  showToast('Beneficiary registry refreshed', 'info');
  if (btn) btn.disabled = false;
}

/**
 * Called when search input or region filter changes
 */
function onSearchOrFilterChange() {
  currentPage = 1;
  applyFilteringAndPagination();
}

/**
 * Filters the list by search keyword and region, then renders the current page
 */
function applyFilteringAndPagination() {
  const search = (document.getElementById('ben-search')?.value || '').trim().toLowerCase();
  const region = document.getElementById('ben-filter-region')?.value || '';

  filteredBeneficiaries = allBeneficiaries.filter(b => {
    const matchesSearch = !search ||
      (b.name && b.name.toLowerCase().includes(search)) ||
      (b.beneficiary_id && b.beneficiary_id.toLowerCase().includes(search)) ||
      (b.ration_card_number && b.ration_card_number.toLowerCase().includes(search));

    const matchesRegion = !region || b.region === region;
    return matchesSearch && matchesRegion;
  });

  const total = filteredBeneficiaries.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (currentPage > totalPages) currentPage = totalPages;

  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, total);
  const pageSlice = filteredBeneficiaries.slice(startIndex, endIndex);

  renderBeneficiariesTable(pageSlice);
  renderPaginationControls(total, totalPages, startIndex, endIndex);
}

/**
 * Safely renders the cardholders directory table with Edit and Delete actions.
 */
function renderBeneficiariesTable(beneficiaries) {
  const tbody = document.getElementById('beneficiaries-tbody');
  if (!tbody) return;

  if (!beneficiaries || beneficiaries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding: 1.5rem;">No cardholders found matching search criteria.</td></tr>';
    return;
  }

  tbody.innerHTML = beneficiaries.map(b => {
    const safeBid = escapeHtml(b.beneficiary_id);
    const safeName = escapeHtml(b.name);
    const safeRegion = escapeHtml(b.region);
    const safeSize = Number(b.family_size) || 1;
    const rawType = b.ration_card_type || 'Priority (PHH)';
    const safeType = escapeHtml(rawType);
    const safeCardNum = escapeHtml(b.ration_card_number || `RC-${b.beneficiary_id}`);
    const category = normalizeRationCardType(rawType);
    const badgeTypeClass = category === 'NPHH'
      ? 'badge-info'
      : (category === 'AAY' ? 'badge-purple' : 'badge-warning');

    const catLabel = category === 'AAY' ? 'AAY' : (category === 'PHH' ? 'PHH' : 'NPHH');
    const catSub = category === 'AAY' ? 'Antyodaya' : (category === 'PHH' ? 'Priority' : 'Non-Priority');

    const quota = computeMonthlyQuota(rawType, safeSize, b.monthly_quota, b.entitlement);
    const quotaHtml = quota.tableHtml;

    return `
      <tr>
        <td>
          <strong>${safeBid}</strong>
          <div style="font-size:0.72rem; color:var(--text-secondary); margin-top: 2px;">
            <i class="fa-solid fa-id-card" style="margin-right: 3px; font-size: 0.68rem; color: var(--text-muted);"></i>${safeCardNum}
          </div>
        </td>
        <td><strong>${safeName}</strong></td>
        <td><span class="badge badge-info">${safeRegion}</span></td>
        <td style="text-align: center; white-space: nowrap;"><strong>${safeSize}</strong> <span style="font-size:0.72rem; color:var(--text-secondary);">${safeSize === 1 ? 'member' : 'members'}</span></td>
        <td>
          <span class="badge ${badgeTypeClass}" title="${safeType}">${catLabel}</span>
          <div style="font-size:0.72rem; color:var(--text-secondary); margin-top: 2px;">${catSub}</div>
        </td>
        <td>${quotaHtml}</td>
        <td style="text-align: center;"><span class="badge badge-success"><i class="fa-solid fa-circle-check" style="font-size:0.65rem;"></i> Active</span></td>
        <td style="text-align: right;">
          <div style="display: inline-flex; gap: 6px; align-items: center; justify-content: flex-end;">
            <button class="btn btn-secondary btn-sm" title="Edit Cardholder" onclick="openEditBeneficiaryModal('${safeBid}')">
              <i class="fa-solid fa-pen-to-square"></i> Edit
            </button>
            <button class="btn btn-secondary btn-sm" title="Safe Delete Cardholder" onclick="promptSafeDeleteBeneficiary('${safeBid}', '${safeName.replace(/'/g, "\\'")}', '${safeCardNum}', '${safeRegion}')" style="color:var(--accent-rose);">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * Renders responsive pagination controls and summary range counter
 */
function renderPaginationControls(total, totalPages, startIndex, endIndex) {
  const infoEl = document.getElementById('ben-pagination-info');
  const controlsEl = document.getElementById('ben-pagination-controls');
  if (!infoEl || !controlsEl) return;

  if (total === 0) {
    infoEl.textContent = 'Showing 0 cardholders';
    controlsEl.innerHTML = '';
    return;
  }

  infoEl.innerHTML = `Showing <strong>${startIndex + 1}</strong> to <strong>${endIndex}</strong> of <strong>${total}</strong> registered cardholders`;

  if (totalPages <= 1) {
    controlsEl.innerHTML = '';
    return;
  }

  let html = `
    <button class="btn btn-secondary btn-sm" onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>
      <i class="fa-solid fa-chevron-left"></i> Prev
    </button>
  `;

  for (let i = 1; i <= totalPages; i++) {
    const isActive = i === currentPage;
    html += `
      <button class="btn ${isActive ? 'btn-primary' : 'btn-secondary'} btn-sm" style="min-width: 32px; padding: 4px 8px; font-weight: ${isActive ? '700' : '400'};" onclick="goToPage(${i})">
        ${i}
      </button>
    `;
  }

  html += `
    <button class="btn btn-secondary btn-sm" onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>
      Next <i class="fa-solid fa-chevron-right"></i>
    </button>
  `;

  controlsEl.innerHTML = html;
}

function goToPage(page) {
  const totalPages = Math.max(1, Math.ceil(filteredBeneficiaries.length / pageSize));
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  applyFilteringAndPagination();
}

/**
 * Opens Edit Modal and populates existing cardholder data
 */
function openEditBeneficiaryModal(bid) {
  const b = allBeneficiaries.find(x => x.beneficiary_id === bid);
  if (!b) {
    showToast(`Beneficiary ${bid} not found in active list`, 'error');
    return;
  }

  document.getElementById('edit-ben-id').value = b.beneficiary_id;
  document.getElementById('edit-ben-id-display').value = b.beneficiary_id;
  document.getElementById('edit-ben-name').value = b.name || '';
  document.getElementById('edit-ben-region').value = b.region || 'Chennai';
  document.getElementById('edit-ben-size').value = b.family_size || 4;
  document.getElementById('edit-ben-type').value = b.ration_card_type || 'Priority (PHH)';
  document.getElementById('edit-ben-card-num').value = b.ration_card_number || `RC-${b.beneficiary_id}`;

  updateEditEntitlementPreview();
  openModal('edit-beneficiary-modal');
}

/**
 * Opens Safe Delete Confirmation Modal with cardholder details.
 */
function promptSafeDeleteBeneficiary(bid, name, cardNum, region) {
  targetDeleteBeneficiaryId = bid;
  document.getElementById('del-ben-id-display').textContent = bid;
  document.getElementById('del-ben-name-display').textContent = name;
  document.getElementById('del-ben-card-display').textContent = cardNum;
  document.getElementById('del-ben-region-display').textContent = region;
  openModal('delete-beneficiary-modal');
}

/**
 * Executes safe delete against backend API with audit/transaction protection.
 */
async function executeSafeDeleteBeneficiary() {
  if (!targetDeleteBeneficiaryId) return;

  const confirmBtn = document.getElementById('btn-confirm-delete-ben');
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking Audit Protection...';
  }

  try {
    const res = await API.deleteBeneficiary(targetDeleteBeneficiaryId);
    if (res && res.status === 'success') {
      showToast(`Beneficiary ${targetDeleteBeneficiaryId} deleted successfully.`, 'info');
      closeModal('delete-beneficiary-modal');
      await fetchBeneficiaries(false);
      try { localStorage.setItem('smart_pds_beneficiary_updated', Date.now().toString()); } catch (_) {}
    }
  } catch (err) {
    // If blocked by backend transaction protection, display clear explanation toast
    showToast(err.message || `Cannot delete beneficiary ${targetDeleteBeneficiaryId}`, 'error');
  } finally {
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Confirm Delete';
    }
  }
}
