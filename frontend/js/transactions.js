/**
 * AI-Powered Smart PDS - Transactions Controller
 */

let allTransactions = [];
let txnCurrentPage = 1;
const TXN_PAGE_SIZE = 15;

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

  const form = document.getElementById('new-txn-form');
  if (form) {
    // Reset errors when user types
    form.addEventListener('input', () => {
      const errBox = document.getElementById('txn-error-box');
      if (errBox) errBox.style.display = 'none';
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btn-submit-txn');
      const errBox = document.getElementById('txn-error-box');
      const errMsg = document.getElementById('txn-error-msg');
      if (errBox) errBox.style.display = 'none';

      const benId = document.getElementById('txn-ben-id').value.trim();
      const commodity = document.getElementById('txn-commodity').value;
      const region = document.getElementById('txn-region').value;
      const qty = parseFloat(document.getElementById('txn-qty').value);

      // Client-side pre-validations
      if (!benId) {
        showFormError('Beneficiary ID is required');
        return;
      }
      if (!commodity) {
        showFormError('Please select a valid commodity');
        return;
      }
      if (!qty || isNaN(qty) || qty <= 0) {
        showFormError('Distribution quantity must be greater than zero');
        return;
      }
      if (qty > 200) {
        showFormError('Quantity exceeds single transaction safety limit (200 kg)');
        return;
      }

      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

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
          let toastText = `Transaction ${d.transaction_id} recorded! Stock remaining: ${d.remaining_stock} kg.`;

          if (res.entitlement_warning) {
            toastText += ` (${res.entitlement_warning})`;
          }

          if (d.status === 'SUSPICIOUS') {
            showToast(`⚠️ ${d.transaction_id} FLAGGED: ${d.reason}`, 'warning');
          } else {
            showToast(toastText, 'success');
          }

          closeModal('new-txn-modal');
          form.reset();
          document.getElementById('txn-ben-id').value = '';
          document.getElementById('txn-qty').value = '';
          txnCurrentPage = 1;
          await loadTransactions();
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
});

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
    const res = await API.getTransactions({ limit: 200 });
    if (res && res.status === 'success') {
      allTransactions = res.data || [];
      filterTransactions();
    }
  } catch (err) {
    showToast('Failed to load transactions', 'error');
  }
}

function renderTransactionsTable(txns) {
  const tbody = document.getElementById('txns-tbody');
  if (!tbody) return;

  if (!txns || txns.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:var(--text-muted); padding:2rem;">No grain distribution transactions found.</td></tr>';
    updatePaginationUI(0);
    return;
  }

  // Pagination calculation
  const totalPages = Math.ceil(txns.length / TXN_PAGE_SIZE);
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

    return `
      <tr>
        <td><strong>${escapeHtml(t.transaction_id)}</strong></td>
        <td>${escapeHtml(t.beneficiary_id)}</td>
        <td><span class="badge badge-info">${escapeHtml(t.commodity)}</span></td>
        <td class="text-right"><strong>${t.quantity} kg</strong></td>
        <td>${escapeHtml(t.ration_shop_id || '-')}</td>
        <td>${escapeHtml(t.region || '-')}</td>
        <td style="font-size:0.82rem; color:var(--text-muted); white-space:nowrap;">${timeStr}</td>
        <td><span class="badge ${badgeClass}">${escapeHtml(statusLabel)} (${escapeHtml(riskLabel)})</span></td>
        <td style="max-width:200px; font-size:0.8rem; color:var(--text-secondary);">${escapeHtml(t.reason || 'Normal entitlement distribution')}</td>
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

  const totalPages = Math.ceil(totalItems / TXN_PAGE_SIZE);
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
  filterTransactions();
}

function filterTransactions() {
  const searchEl = document.getElementById('txn-search');
  const statusEl = document.getElementById('txn-filter-status');
  const commodityEl = document.getElementById('txn-filter-commodity');

  const search = (searchEl ? searchEl.value : '').toLowerCase().trim();
  const status = statusEl ? statusEl.value : '';
  const commodity = commodityEl ? commodityEl.value : '';

  const filtered = allTransactions.filter(t => {
    const matchSearch = !search ||
      (t.transaction_id || '').toLowerCase().includes(search) ||
      (t.beneficiary_id || '').toLowerCase().includes(search);
    const matchStatus = !status || t.status === status;
    const matchCom = !commodity || t.commodity === commodity;
    return matchSearch && matchStatus && matchCom;
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

/** Display detailed transaction breakdown, ML anomaly evaluation, and audit trail */
async function viewTransactionDetails(txnId) {
  const modalBody = document.getElementById('txn-detail-body');
  if (!modalBody) return;

  // Find transaction from cached list or fetch via API
  let txn = allTransactions.find(t => t.transaction_id === txnId);
  if (!txn) {
    try {
      const res = await API.request(`/transactions/${encodeURIComponent(txnId)}`);
      if (res && res.status === 'success') txn = res.data;
    } catch (_) { }
  }

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
  const anomalyScore = txn.anomaly_score !== undefined ? Number(txn.anomaly_score).toFixed(4) : 'N/A';
  const prevStockStr = txn.previous_stock !== undefined && txn.previous_stock !== null ? `${txn.previous_stock} kg` : '-';
  const remStockStr = txn.remaining_stock !== undefined && txn.remaining_stock !== null ? `${txn.remaining_stock} kg` : '-';

  // Build audit trail steps
  const auditEvents = txn.audit_trail || [
    {
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
          <strong style="font-size:0.82rem; color:var(--text-primary);">${escapeHtml(evt.action || 'EVENT')}</strong>
          <span style="font-size:0.75rem; color:var(--text-muted);">${formatLocalTime(evt.timestamp)}</span>
        </div>
        <p style="margin:0; font-size:0.8rem; color:var(--text-secondary);">${escapeHtml(evt.details || '')}</p>
      </div>
    </div>
  `).join('');

  modalBody.innerHTML = `
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px;">
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Transaction ID</span>
        <div style="font-weight:600; font-size:1rem; color:var(--text-primary);">${escapeHtml(txn.transaction_id)}</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Processing Status</span>
        <div><span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> ${escapeHtml(processingStatus)}</span></div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Beneficiary ID</span>
        <div style="font-weight:600; color:var(--text-primary);">${escapeHtml(txn.beneficiary_id)}</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Grain Distributed</span>
        <div style="font-weight:600; color:var(--text-primary);">${escapeHtml(txn.commodity)} (${escapeHtml(txn.commodity_code || '-')}) — <strong>${txn.quantity} kg</strong></div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Depot & Region</span>
        <div style="color:var(--text-secondary);">${escapeHtml(txn.ration_shop_id || '-')} (${escapeHtml(txn.region || 'Chennai')})</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Stock Impact (Previous → New)</span>
        <div style="color:var(--text-secondary);">${prevStockStr} → <strong style="color:var(--accent-cyan);">${remStockStr}</strong></div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); grid-column:span 2;">
        <span style="font-size:0.75rem; color:var(--text-muted);">ML Pipeline Risk & Anomaly Assessment</span>
        <div style="display:flex; align-items:center; gap:8px; margin-top:4px;">
          <span class="badge ${badgeClass}">${escapeHtml(txn.status)} (${escapeHtml(txn.risk_level || 'LOW')})</span>
          <span style="font-size:0.8rem; color:var(--text-secondary);">Score: <code>${anomalyScore}</code></span>
        </div>
        <div style="margin-top:6px; font-size:0.8rem; color:var(--text-muted);">${escapeHtml(txn.reason || 'Normal entitlement distribution')}</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); grid-column:span 2;">
        <span style="font-size:0.75rem; color:var(--text-muted);">Distribution Timestamp (Local Time)</span>
        <div style="font-size:0.85rem; color:var(--text-secondary); font-family:monospace;">${timeStr}</div>
      </div>
    </div>

    <h4 style="font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-muted); margin-bottom:12px;">
      <i class="fa-solid fa-timeline" style="color:var(--accent-cyan);"></i> Audit Trail Events
    </h4>
    <div style="max-height:200px; overflow-y:auto; padding-right:4px;">
      ${auditHtml}
    </div>
  `;

  openModal('txn-detail-modal');
}
