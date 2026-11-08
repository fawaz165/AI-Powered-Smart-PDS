/**
 * AI-Powered Smart PDS - Transactions Controller
 * Secure, auditable transaction ledger with real-time entitlement validation,
 * Isolation Forest anomaly diagnostics, and human officer review history.
 */

let allTransactions = [];
let txnCurrentPage = 1;
const TXN_PAGE_SIZE = 15;
let quotaLookupTimer = null;

/** XSS-safe HTML escaping */
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(String(str)));
  return div.innerHTML;
}

/** Format timestamp safely into local time */
function formatLocalTime(timestamp) {
  if (!timestamp) return 'N/A';
  try {
    const raw = (typeof timestamp === 'object' && timestamp.$date) ? timestamp.$date : timestamp;
    const d = new Date(raw);
    if (!isNaN(d.getTime())) {
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
  } catch (_) { }
  return 'N/A';
}

document.addEventListener('DOMContentLoaded', async () => {
  await populateTransactionCommodityDropdowns();
  await loadTransactions();

  const benInput = document.getElementById('txn-ben-id');
  const comInput = document.getElementById('txn-commodity');
  const qtyInput = document.getElementById('txn-qty');

  // Debounced beneficiary entitlement preview in the distribution modal
  if (benInput) {
    benInput.addEventListener('input', scheduleQuotaPreview);
  }
  if (comInput) {
    comInput.addEventListener('change', scheduleQuotaPreview);
  }
  if (qtyInput) {
    qtyInput.addEventListener('input', scheduleQuotaPreview);
  }

  const form = document.getElementById('new-txn-form');
  if (form) {
    // Reset errors when user edits
    form.addEventListener('input', () => {
      const errBox = document.getElementById('txn-error-box');
      if (errBox) errBox.style.display = 'none';
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btn-submit-txn');
      const errBox = document.getElementById('txn-error-box');
      if (errBox) errBox.style.display = 'none';

      const benId = document.getElementById('txn-ben-id').value.trim();
      const commodity = document.getElementById('txn-commodity').value;
      const region = document.getElementById('txn-region').value;
      const rawQty = document.getElementById('txn-qty').value;
      const qty = parseFloat(rawQty);

      // Strict client-side pre-validations
      if (!benId) {
        showFormError('Beneficiary ID is required.');
        return;
      }
      if (!commodity) {
        showFormError('Please select a valid grain commodity.');
        return;
      }
      if (rawQty.trim() === '' || isNaN(qty) || qty <= 0) {
        showFormError('Distribution quantity must be greater than zero.');
        return;
      }
      if (qty > 200) {
        showFormError('Quantity exceeds single transaction safety limit (200 kg).');
        return;
      }

      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Authorizing...';

      try {
        const res = await API.distributeGrain({
          beneficiary_id: benId,
          commodity: commodity,
          quantity: qty,
          region: region,
          ration_shop_id: `FPS-${region.substring(0, 3).toUpperCase()}-001`
        });

        if (res && res.status === 'success') {
          const d = res.data;
          let toastText = `Transaction ${d.transaction_id} recorded! Warehouse remaining: ${Math.round(d.remaining_stock).toLocaleString()} kg.`;

          if (res.entitlement_warning) {
            toastText += ` (${res.entitlement_warning})`;
          }

          if (d.status === 'SUSPICIOUS') {
            showToast(`⚠️ Anomaly Flagged (${d.transaction_id}): ${d.reason}`, 'warning');
          } else {
            showToast(toastText, 'success');
          }

          // Trigger cross-page dashboard and inventory sync
          try {
            localStorage.setItem('smart_pds_inventory_updated', Date.now().toString());
          } catch (_) {}

          closeModal('new-txn-modal');
          form.reset();
          const quotaBox = document.getElementById('txn-quota-info');
          if (quotaBox) quotaBox.style.display = 'none';

          txnCurrentPage = 1;
          await loadTransactions();
        } else {
          showFormError(res.message || 'Transaction rejected by server.');
        }
      } catch (err) {
        const errorText = err.message || 'Transaction rejected by server';
        showFormError(errorText);
        showToast(errorText, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-check"></i> Authorize & Distribute';
      }
    });
  }

  // Cross-tab synchronization
  window.addEventListener('storage', (e) => {
    if (e.key === 'smart_pds_inventory_updated') {
      loadTransactions();
    }
  });
});

/**
 * Debounced live entitlement check when filling distribution form.
 */
function scheduleQuotaPreview() {
  clearTimeout(quotaLookupTimer);
  quotaLookupTimer = setTimeout(async () => {
    const benId = (document.getElementById('txn-ben-id')?.value || '').trim().toUpperCase();
    const com = document.getElementById('txn-commodity')?.value;
    const qty = parseFloat(document.getElementById('txn-qty')?.value || '0');
    const infoBox = document.getElementById('txn-quota-info');
    const infoText = document.getElementById('txn-quota-text');

    if (!benId || !infoBox || !infoText) {
      if (infoBox) infoBox.style.display = 'none';
      return;
    }

    try {
      const res = await API.getBeneficiaries({ search: benId, limit: 1 });
      if (res && res.status === 'success' && res.data && res.data.length > 0) {
        const ben = res.data.find(b => b.beneficiary_id === benId) || res.data[0];
        if (ben.beneficiary_id === benId) {
          const quota = ben.monthly_quota ? (ben.monthly_quota[com] || 0) : 0;
          let msg = `<strong>${escapeHtml(ben.name)}</strong> (${escapeHtml(ben.ration_card_type)}, ${ben.family_size} members) &bull; Monthly ${escapeHtml(com)} Quota: <strong>${quota} kg</strong>`;

          if (qty > 0 && quota > 0 && qty > quota) {
            msg += `<br><span style="color:#fbbf24;"><i class="fa-solid fa-triangle-exclamation"></i> Warning: Requested ${qty} kg exceeds monthly quota (${quota} kg). Will trigger ML anomaly flag.</span>`;
          }

          infoText.innerHTML = msg;
          infoBox.style.display = 'block';
          return;
        }
      }
      infoBox.style.display = 'none';
    } catch (_) {
      infoBox.style.display = 'none';
    }
  }, 350);
}

function showFormError(msg) {
  const errBox = document.getElementById('txn-error-box');
  const errMsg = document.getElementById('txn-error-msg');
  if (errBox && errMsg) {
    errMsg.textContent = msg;
    errBox.style.display = 'block';
  }
}

async function loadTransactions() {
  try {
    const res = await API.getTransactions({ limit: 300 });
    if (res && res.status === 'success') {
      allTransactions = res.data || [];
      filterTransactions();
    }
  } catch (err) {
    console.error('Failed to load transactions:', err);
    showToast('Failed to load transaction records from server.', 'error');
  }
}

function renderTransactionsTable(txns) {
  const tbody = document.getElementById('txns-tbody');
  if (!tbody) return;

  if (!txns || txns.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:var(--text-muted); padding:2rem;">No matching transactions found for current search/filter.</td></tr>';
    updatePaginationUI(0);
    return;
  }

  // Pagination calculation
  const totalPages = Math.ceil(txns.length / TXN_PAGE_SIZE) || 1;
  if (txnCurrentPage > totalPages) txnCurrentPage = totalPages;
  if (txnCurrentPage < 1) txnCurrentPage = 1;
  const start = (txnCurrentPage - 1) * TXN_PAGE_SIZE;
  const pageItems = txns.slice(start, start + TXN_PAGE_SIZE);

  tbody.innerHTML = pageItems.map(t => {
    let badgeClass = 'badge-success';
    if (t.risk_level === 'HIGH' || t.status === 'SUSPICIOUS') {
      badgeClass = 'badge-danger';
    } else if (t.risk_level === 'MEDIUM') {
      badgeClass = 'badge-warning';
    }

    const timeStr = formatLocalTime(t.timestamp);
    const statusLabel = t.status === 'NORMAL' ? 'Normal' : t.status;
    const riskLabel = t.risk_level || 'LOW';

    // Review status badge if officer audited
    let reviewPill = '';
    if (t.review_status === 'VERIFIED_LEGITIMATE') {
      reviewPill = ` <span class="badge badge-success" style="font-size:0.7rem; margin-top:2px;" title="Audited by officer ${escapeHtml(t.reviewed_by || '')}"><i class="fa-solid fa-circle-check"></i> Legitimate</span>`;
    } else if (t.review_status === 'CONFIRMED_IRREGULARITY') {
      reviewPill = ` <span class="badge badge-danger" style="font-size:0.7rem; margin-top:2px;" title="Confirmed irregularity by officer ${escapeHtml(t.reviewed_by || '')}"><i class="fa-solid fa-triangle-exclamation"></i> Irregular</span>`;
    }

    return `
      <tr>
        <td><strong>${escapeHtml(t.transaction_id)}</strong></td>
        <td><code>${escapeHtml(t.beneficiary_id)}</code></td>
        <td><span class="badge badge-info">${escapeHtml(t.commodity)}</span></td>
        <td class="text-right"><strong>${Number(t.quantity).toFixed(1)} kg</strong></td>
        <td>${escapeHtml(t.ration_shop_id || '-')}</td>
        <td><span class="badge badge-secondary">${escapeHtml(t.region || '-')}</span></td>
        <td style="font-size:0.82rem; color:var(--text-muted); white-space:nowrap;">${timeStr}</td>
        <td>
          <span class="badge ${badgeClass}">${escapeHtml(statusLabel)} (${escapeHtml(riskLabel)})</span>
          ${reviewPill}
        </td>
        <td style="max-width:240px; font-size:0.8rem; color:var(--text-secondary); line-height:1.3;">
          ${escapeHtml(t.reason || 'Conforms to cardholder monthly entitlement schedule.')}
        </td>
        <td>
          <button class="btn btn-secondary btn-xs" style="padding:4px 8px; font-size:0.75rem;" onclick="viewTransactionDetails('${escapeHtml(t.transaction_id)}')">
            <i class="fa-solid fa-eye"></i> Details
          </button>
        </td>
      </tr>
    `;
  }).join('');

  updatePaginationUI(txns.length);
}

function updatePaginationUI(totalItems) {
  let paginationEl = document.getElementById('txn-pagination');
  if (!paginationEl) {
    const tablePanel = document.querySelector('.data-panel .table-responsive');
    if (!tablePanel) return;
    paginationEl = document.createElement('div');
    paginationEl.id = 'txn-pagination';
    paginationEl.style.cssText = 'display:flex; align-items:center; justify-content:space-between; padding:12px 14px; border-top:1px solid var(--border-subtle); font-size:0.82rem; color:var(--text-secondary);';
    tablePanel.parentElement.appendChild(paginationEl);
  }

  if (totalItems === 0) {
    paginationEl.innerHTML = '<span>No transactions</span>';
    return;
  }

  const totalPages = Math.ceil(totalItems / TXN_PAGE_SIZE) || 1;
  const start = (txnCurrentPage - 1) * TXN_PAGE_SIZE + 1;
  const end = Math.min(txnCurrentPage * TXN_PAGE_SIZE, totalItems);

  paginationEl.innerHTML = `
    <span>Showing <strong>${start}–${end}</strong> of <strong>${totalItems}</strong> distributions</span>
    <div style="display:flex; gap:6px; align-items:center;">
      <button class="btn btn-secondary btn-sm" ${txnCurrentPage <= 1 ? 'disabled' : ''} onclick="txnGoPage(${txnCurrentPage - 1})">
        <i class="fa-solid fa-chevron-left"></i> Prev
      </button>
      <span style="padding:4px 10px; color:var(--text-primary); font-weight:500;">Page ${txnCurrentPage} of ${totalPages}</span>
      <button class="btn btn-secondary btn-sm" ${txnCurrentPage >= totalPages ? 'disabled' : ''} onclick="txnGoPage(${txnCurrentPage + 1})">
        Next <i class="fa-solid fa-chevron-right"></i>
      </button>
    </div>
  `;
}

function txnGoPage(page) {
  txnCurrentPage = page;
  filterTransactions(false);
}

/**
 * Filter transactions by search text, district, status, and commodity.
 * Resets to page 1 on active filter changes.
 */
function filterTransactions(resetPage = true) {
  if (resetPage) txnCurrentPage = 1;

  const searchEl = document.getElementById('txn-search');
  const regionEl = document.getElementById('txn-filter-region');
  const statusEl = document.getElementById('txn-filter-status');
  const commodityEl = document.getElementById('txn-filter-commodity');

  const search = (searchEl ? searchEl.value : '').toLowerCase().trim();
  const region = regionEl ? regionEl.value : '';
  const status = statusEl ? statusEl.value : '';
  const commodity = commodityEl ? commodityEl.value : '';

  const filtered = allTransactions.filter(t => {
    const matchSearch = !search ||
      (t.transaction_id || '').toLowerCase().includes(search) ||
      (t.beneficiary_id || '').toLowerCase().includes(search) ||
      (t.ration_shop_id || '').toLowerCase().includes(search);
    const matchRegion = !region || (t.region && t.region.toLowerCase() === region.toLowerCase());
    const matchStatus = !status || t.status === status;
    const matchCom = !commodity || t.commodity === commodity || t.commodity_code === commodity;
    return matchSearch && matchRegion && matchStatus && matchCom;
  });

  renderTransactionsTable(filtered);
}

async function populateTransactionCommodityDropdowns() {
  const select = document.getElementById('txn-commodity');
  const filterSelect = document.getElementById('txn-filter-commodity');
  try {
    const res = await API.getCommodities();
    if (res && res.status === 'success' && res.data && res.data.length > 0) {
      if (select) {
        select.innerHTML = res.data.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.commodity_code)})</option>`).join('');
      }
      if (filterSelect) {
        const cur = filterSelect.value;
        filterSelect.innerHTML = '<option value="">All Grains</option>' + res.data.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.commodity_code)})</option>`).join('');
        filterSelect.value = cur;
      }
    }
  } catch (e) {
    console.warn('Could not populate transaction commodity dropdowns:', e);
  }
}

/**
 * Comprehensive transaction details view showing:
 * 1. Beneficiary Entitlement Quota
 * 2. Previous Monthly Distributions & Remaining Balance
 * 3. Atomic Warehouse Stock Deduction
 * 4. ML Anomaly Diagnostics (Isolation Forest Score, Interpretation)
 * 5. Official Administrative Review Audit Trail
 */
async function viewTransactionDetails(txnId) {
  const modalBody = document.getElementById('txn-detail-body');
  if (!modalBody) return;

  // Retrieve full transaction document
  let txn = allTransactions.find(t => t.transaction_id === txnId);
  try {
    const res = await API.request(`/transactions/${encodeURIComponent(txnId)}`);
    if (res && res.status === 'success' && res.data) {
      txn = res.data;
    }
  } catch (_) { }

  if (!txn) {
    showToast('Transaction details not found', 'error');
    return;
  }

  let badgeClass = 'badge-success';
  if (txn.risk_level === 'HIGH' || txn.status === 'SUSPICIOUS') {
    badgeClass = 'badge-danger';
  } else if (txn.risk_level === 'MEDIUM') {
    badgeClass = 'badge-warning';
  }

  const timeStr = formatLocalTime(txn.timestamp);
  const processingStatus = txn.processing_status || 'COMPLETED';
  const anomalyScore = txn.anomaly_score !== undefined ? Number(txn.anomaly_score).toFixed(4) : '0.0000';
  const prevStockStr = txn.previous_stock !== undefined && txn.previous_stock !== null ? `${Math.round(txn.previous_stock).toLocaleString()} kg` : '-';
  const remStockStr = txn.remaining_stock !== undefined && txn.remaining_stock !== null ? `${Math.round(txn.remaining_stock).toLocaleString()} kg` : '-';

  const entitledQuotaStr = txn.entitled_quota !== undefined && txn.entitled_quota !== null ? `${txn.entitled_quota} kg/month` : 'Standard Scheme Quota';
  const alreadyDistStr = txn.already_distributed !== undefined && txn.already_distributed !== null ? `${txn.already_distributed} kg` : '0 kg';
  const remEntitlementStr = txn.remaining_entitlement !== undefined && txn.remaining_entitlement !== null ? `${txn.remaining_entitlement} kg` : 'Full Quota Available';

  // Audit review decision block (if reviewed by an authorized officer)
  let reviewDecisionHtml = '';
  if (txn.review_decision || txn.reviewed_by) {
    const decisionBadge = (txn.review_status === 'VERIFIED_LEGITIMATE' || txn.review_decision === 'VERIFIED_LEGITIMATE' || txn.review_decision === 'APPROVED_GENUINE')
      ? '<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> Verified Legitimate</span>'
      : '<span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> Confirmed Irregularity</span>';

    reviewDecisionHtml = `
      <div style="background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.25); border-radius: var(--radius-sm); padding: 12px 14px; margin-bottom: 16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <strong style="color:var(--text-primary); font-size:0.85rem;"><i class="fa-solid fa-user-shield" style="color:var(--accent-emerald);"></i> Official Administrative Review Decision</strong>
          ${decisionBadge}
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:0.8rem; color:var(--text-secondary); margin-bottom:6px;">
          <div>Officer ID: <strong>${escapeHtml(txn.reviewed_by || 'Admin')}</strong></div>
          <div>Reviewed At: <strong>${formatLocalTime(txn.reviewed_at)}</strong></div>
        </div>
        <div style="font-size:0.8rem; color:var(--text-muted); background:rgba(0,0,0,0.2); padding:6px 10px; border-radius:4px;">
          <strong>Officer Justification:</strong> ${escapeHtml(txn.review_reason || 'Administrative review completed.')}
        </div>
      </div>
    `;
  } else if (txn.status === 'SUSPICIOUS') {
    reviewDecisionHtml = `
      <div style="background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.25); border-radius: var(--radius-sm); padding: 10px 14px; margin-bottom: 16px; font-size:0.82rem; color:#fcd34d;">
        <i class="fa-solid fa-shield-halved"></i> <strong>Pending Administrative Review:</strong> This transaction was flagged as a statistical anomaly by the ML Isolation Forest pipeline. In accordance with Smart PDS audit policy, anomalies alone do NOT constitute unilateral proof of fraud and await human verification.
      </div>
    `;
  }

  // Build audit trail steps
  const auditEvents = txn.audit_trail || [
    {
      step: 1,
      action: 'TRANSACTION_INITIALIZED',
      timestamp: timeStr,
      details: `Distributed ${txn.quantity} kg ${txn.commodity} at ${txn.ration_shop_id || 'Depot'}`
    }
  ];

  const auditHtml = auditEvents.map((evt, idx) => `
    <div style="display:flex; gap:12px; margin-bottom:12px; position:relative;">
      <div style="width:24px; height:24px; border-radius:50%; background:var(--primary); color:#fff; display:flex; align-items:center; justify-content:center; font-size:0.75rem; font-weight:bold; flex-shrink:0;">
        ${evt.step || (idx + 1)}
      </div>
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:8px 12px; flex:1;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
          <strong style="font-size:0.82rem; color:var(--text-primary);">${escapeHtml(evt.action || 'AUDIT_EVENT')}</strong>
          <span style="font-size:0.75rem; color:var(--text-muted);">${formatLocalTime(evt.timestamp)}</span>
        </div>
        <p style="margin:0; font-size:0.8rem; color:var(--text-secondary); line-height:1.3;">
          ${escapeHtml(evt.details || evt.reason || '')}
        </p>
      </div>
    </div>
  `).join('');

  modalBody.innerHTML = `
    ${reviewDecisionHtml}

    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px;">
      <!-- Row 1: Identifiers -->
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Transaction ID</span>
        <div style="font-weight:600; font-size:1rem; color:var(--text-primary);">${escapeHtml(txn.transaction_id)}</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Distribution Status</span>
        <div><span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> ${escapeHtml(processingStatus)}</span></div>
      </div>

      <!-- Row 2: Beneficiary & Entitlement Profile -->
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Beneficiary Cardholder</span>
        <div style="font-weight:600; color:var(--text-primary);"><code>${escapeHtml(txn.beneficiary_id)}</code></div>
        <div style="font-size:0.75rem; color:var(--text-muted); margin-top:3px;">
          Monthly Quota: <strong>${entitledQuotaStr}</strong>
        </div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Monthly Entitlement Balances</span>
        <div style="font-size:0.8rem; color:var(--text-secondary);">Drawn Prior: <strong>${alreadyDistStr}</strong></div>
        <div style="font-size:0.8rem; color:var(--accent-emerald);">Remaining at Draw: <strong>${remEntitlementStr}</strong></div>
      </div>

      <!-- Row 3: Grain & Stock Impact -->
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Grain Distributed</span>
        <div style="font-weight:600; color:var(--text-primary);">${escapeHtml(txn.commodity)} (${escapeHtml(txn.commodity_code || '-')}) — <span style="color:var(--accent-cyan);">${Number(txn.quantity).toFixed(1)} kg</span></div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Warehouse Stock Deduction</span>
        <div style="color:var(--text-secondary); font-size:0.85rem;">${prevStockStr} → <strong style="color:var(--accent-cyan);">${remStockStr}</strong> (-${Number(txn.quantity).toFixed(1)} kg)</div>
      </div>

      <!-- Row 4: Depot Location & Timestamp -->
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Fair Price Shop & District</span>
        <div style="color:var(--text-secondary); font-size:0.85rem;">${escapeHtml(txn.ration_shop_id || '-')} (${escapeHtml(txn.region || 'Chennai')})</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Local Distribution Timestamp</span>
        <div style="font-size:0.85rem; color:var(--text-secondary); font-family:monospace;">${timeStr}</div>
      </div>

      <!-- Row 5: ML Pipeline Assessment -->
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); grid-column:span 2;">
        <span style="font-size:0.75rem; color:var(--text-muted);">ML Isolation Forest Risk Diagnostics</span>
        <div style="display:flex; align-items:center; gap:8px; margin-top:4px;">
          <span class="badge ${badgeClass}">${escapeHtml(txn.status)} (${escapeHtml(txn.risk_level || 'LOW')})</span>
          <span style="font-size:0.8rem; color:var(--text-secondary);">Score: <code>${anomalyScore}</code></span>
        </div>
        <div style="margin-top:6px; font-size:0.8rem; color:var(--text-muted); line-height:1.3;">${escapeHtml(txn.reason || 'Conforms to registered cardholder monthly entitlement schedule.')}</div>
      </div>
    </div>

    <h4 style="font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-muted); margin-bottom:12px;">
      <i class="fa-solid fa-timeline" style="color:var(--accent-cyan);"></i> Immutable Ledger Audit Trail
    </h4>
    <div style="max-height:220px; overflow-y:auto; padding-right:4px;">
      ${auditHtml}
    </div>
  `;

  openModal('txn-detail-modal');
}
