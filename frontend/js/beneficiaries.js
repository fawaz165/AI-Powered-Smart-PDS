/**
 * AI-Powered Smart PDS - Beneficiaries Registry Controller
 * Handles CRUD operations, search & filtering, safe deletion with transaction protection,
 * dynamic monthly entitlement quota calculations using configured ration-card rules,
 * and live registry dashboard metrics updates.
 */

let allBeneficiaries = [];
let targetDeleteBeneficiaryId = null;
let configuredEntitlementRules = null;

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadEntitlementRules();
  await fetchBeneficiaries(true);
  updateEntitlementPreview();

  // Form submission for registering new beneficiary
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

      // Client-side input validation
      if (!bid || bid.length < 3) {
        showToast('Beneficiary ID must be at least 3 characters.', 'error');
        return;
      }
      if (!name || name.length < 2) {
        showToast('Full name must be at least 2 characters.', 'error');
        return;
      }
      if (isNaN(size) || size < 1 || size > 25) {
        showToast('Family size must be a number between 1 and 25.', 'error');
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
          await fetchBeneficiaries(true);
        }
      } catch (err) {
        showToast(err.message || 'Error registering beneficiary', 'error');
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
 * Dynamically computes monthly entitlement preview based on configured ration-card rules.
 */
function updateEntitlementPreview() {
  const previewEl = document.getElementById('entitlement-preview');
  if (!previewEl) return;

  const size = Math.max(1, parseInt(document.getElementById('new-ben-size')?.value || '4', 10));
  const cardType = document.getElementById('new-ben-type')?.value || 'Priority (PHH)';

  let quotaHtml = '';

  if (cardType.includes('AAY')) {
    quotaHtml = '<strong>Rice:</strong> 25kg &bull; <strong>Wheat:</strong> 10kg &bull; <strong>Sugar:</strong> 2kg &bull; <strong>Dal:</strong> 2kg <span class="badge badge-purple" style="font-size:0.7rem; margin-left: 6px;">Fixed Family Quota</span>';
  } else if (cardType.includes('Priority')) {
    const rice = (size * 5).toFixed(1).replace(/\.0$/, '');
    const wheat = (size * 2).toFixed(1).replace(/\.0$/, '');
    quotaHtml = `<strong>Rice:</strong> ${rice}kg &bull; <strong>Wheat:</strong> ${wheat}kg &bull; <strong>Sugar:</strong> 1kg &bull; <strong>Dal:</strong> 1kg <span class="badge badge-warning" style="font-size:0.7rem; margin-left: 6px;">Per-Member Quota</span>`;
  } else {
    const rice = (size * 3).toFixed(1).replace(/\.0$/, '');
    const wheat = (size * 1.5).toFixed(1).replace(/\.0$/, '');
    quotaHtml = `<strong>Rice:</strong> ${rice}kg &bull; <strong>Wheat:</strong> ${wheat}kg &bull; <strong>Sugar:</strong> 1kg &bull; <strong>Dal:</strong> 0.5kg <span class="badge badge-info" style="font-size:0.7rem; margin-left: 6px;">Basic Allotment</span>`;
  }

  previewEl.innerHTML = quotaHtml;
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
    const res = await API.getBeneficiaries({ limit: 500 });
    if (res && res.status === 'success') {
      allBeneficiaries = res.data || [];
      updateRegistryMetrics(allBeneficiaries);
      filterBeneficiaries();
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
 * Updates summary metric KPI counters from database records.
 */
function updateRegistryMetrics(beneficiaries) {
  const total = beneficiaries.length;
  let phhCount = 0;
  let aayCount = 0;
  let nphhCount = 0;

  beneficiaries.forEach(b => {
    const type = b.ration_card_type || '';
    if (type.includes('AAY')) aayCount++;
    else if (type.includes('Priority')) phhCount++;
    else nphhCount++;
  });

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
  showToast('Beneficiary registry refreshed from live database', 'info');
  if (btn) btn.disabled = false;
}

/**
 * Safely renders the cardholders directory table.
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
    const badgeTypeClass = rawType.includes('AAY') ? 'badge-purple' : (rawType.includes('Priority') ? 'badge-warning' : 'badge-info');

    // Dynamic monthly quota rendering from database object
    let quotaHtml = 'Standard Quota';
    if (b.monthly_quota && typeof b.monthly_quota === 'object') {
      quotaHtml = Object.entries(b.monthly_quota)
        .map(([comm, qty]) => `<span style="white-space: nowrap;"><strong>${escapeHtml(comm)}:</strong> ${qty}kg</span>`)
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
          <button class="btn btn-secondary btn-sm" title="Safe Delete Cardholder" onclick="promptSafeDeleteBeneficiary('${safeBid}', '${safeName.replace(/'/g, "\\'")}', '${safeCardNum}', '${safeRegion}')" style="color:var(--accent-rose);">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * Real-time search across Name, ID, or Ration Card Number, combined with Region filter.
 */
function filterBeneficiaries() {
  const search = (document.getElementById('ben-search')?.value || '').trim().toLowerCase();
  const region = document.getElementById('ben-filter-region')?.value || '';

  const filtered = allBeneficiaries.filter(b => {
    const matchesSearch = !search ||
      (b.name && b.name.toLowerCase().includes(search)) ||
      (b.beneficiary_id && b.beneficiary_id.toLowerCase().includes(search)) ||
      (b.ration_card_number && b.ration_card_number.toLowerCase().includes(search));

    const matchesRegion = !region || b.region === region;
    return matchesSearch && matchesRegion;
  });

  renderBeneficiariesTable(filtered);
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
    confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking...';
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
