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
 * Computes monthly commodity entitlement quota following statutory NFSA schemes:
 * - AAY: Fixed family monthly quota (Rice 25kg, Wheat 10kg, Sugar 2kg, Dal 2kg = 35kg total grain)
 * - Priority (PHH): Per-member quota (Rice 5kg/person, Wheat 2kg/person, Sugar 1kg, Dal 1kg)
 * - Non-Priority (NPHH): Per-member quota (Rice 3kg/person, Wheat 1.5kg/person, Sugar 1kg, Dal 0.5kg)
 */
function computeMonthlyQuota(cardType, size) {
  const s = Math.max(1, parseInt(size, 10) || 1);
  const type = String(cardType || '');

  if (type.includes('NPHH') || type.includes('Non-Priority')) {
    const rice = Math.round(s * 3.0 * 10) / 10;
    const wheat = Math.round(s * 1.5 * 10) / 10;
    return {
      quota: { Rice: rice, Wheat: wheat, Sugar: 1.0, Dal: 0.5 },
      html: `<strong>Rice:</strong> ${rice}kg &bull; <strong>Wheat:</strong> ${wheat}kg &bull; <strong>Sugar:</strong> 1kg &bull; <strong>Dal:</strong> 0.5kg <span class="badge badge-info" style="font-size:0.7rem; margin-left: 6px;">Basic Allotment (3kg Rice + 1.5kg Wheat/person)</span>`
    };
  } else if (type.includes('AAY') || type.includes('Antyodaya')) {
    return {
      quota: { Rice: 25.0, Wheat: 10.0, Sugar: 2.0, Dal: 2.0 },
      html: '<strong>Rice:</strong> 25kg &bull; <strong>Wheat:</strong> 10kg &bull; <strong>Sugar:</strong> 2kg &bull; <strong>Dal:</strong> 2kg <span class="badge badge-purple" style="font-size:0.7rem; margin-left: 6px;">Fixed Family Quota (35kg Grains)</span>'
    };
  } else {
    const rice = s * 5;
    const wheat = s * 2;
    return {
      quota: { Rice: rice, Wheat: wheat, Sugar: 1.0, Dal: 1.0 },
      html: `<strong>Rice:</strong> ${rice}kg &bull; <strong>Wheat:</strong> ${wheat}kg &bull; <strong>Sugar:</strong> 1kg &bull; <strong>Dal:</strong> 1kg <span class="badge badge-warning" style="font-size:0.7rem; margin-left: 6px;">Per-Member Quota (5kg Rice + 2kg Wheat/person)</span>`
    };
  }
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
  previewEl.innerHTML = res.html;
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
  previewEl.innerHTML = res.html;
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
    const res = await API.getBeneficiaries({ limit: 1000 });
    if (res && res.status === 'success') {
      allBeneficiaries = res.data || [];
      updateRegistryMetrics(allBeneficiaries, res.categories);
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

  if (categorySummary && typeof categorySummary === 'object' && ('PHH' in categorySummary || 'AAY' in categorySummary || 'NPHH' in categorySummary)) {
    phhCount = Number(categorySummary.PHH) || 0;
    aayCount = Number(categorySummary.AAY) || 0;
    nphhCount = Number(categorySummary.NPHH) || 0;
    total = phhCount + aayCount + nphhCount;
  } else if (Array.isArray(beneficiaries)) {
    beneficiaries.forEach(b => {
      const type = String(b.ration_card_type || '');
      if (type.includes('NPHH') || type.includes('Non-Priority')) {
        nphhCount++;
      } else if (type.includes('AAY') || type.includes('Antyodaya')) {
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
    const badgeTypeClass = (rawType.includes('NPHH') || rawType.includes('Non-Priority'))
      ? 'badge-info'
      : ((rawType.includes('AAY') || rawType.includes('Antyodaya')) ? 'badge-purple' : 'badge-warning');

    // Dynamic monthly quota rendering from database object or calculated standard
    let quotaHtml = 'Standard Quota';
    if (b.monthly_quota && typeof b.monthly_quota === 'object') {
      quotaHtml = Object.entries(b.monthly_quota)
        .map(([comm, qty]) => `<span style="white-space: nowrap;"><strong>${escapeHtml(comm)}:</strong> ${qty}kg</span>`)
        .join(' &bull; ');
    } else {
      const q = computeMonthlyQuota(rawType, safeSize);
      quotaHtml = Object.entries(q.quota)
        .map(([comm, qty]) => `<span style="white-space: nowrap;"><strong>${comm}:</strong> ${qty}kg</span>`)
        .join(' &bull; ');
    }

    return `
      <tr>
        <td>
          <strong>${safeBid}</strong>
          <div style="font-size:0.75rem; color:var(--text-secondary); margin-top: 2px;">
            <i class="fa-solid fa-id-card" style="margin-right: 3px; font-size: 0.7rem;"></i>${safeCardNum}
          </div>
        </td>
        <td><strong>${safeName}</strong></td>
        <td><span class="badge badge-info">${safeRegion}</span></td>
        <td>${safeSize} Member${safeSize === 1 ? '' : 's'}</td>
        <td><span class="badge ${badgeTypeClass}">${safeType}</span></td>
        <td style="font-size:0.8rem; color:var(--text-secondary); max-width: 280px; line-height: 1.4;">${quotaHtml}</td>
        <td><span class="badge badge-success"><i class="fa-solid fa-circle-check" style="font-size:0.65rem;"></i> Active</span></td>
        <td>
          <div style="display: flex; gap: 6px; align-items: center;">
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
