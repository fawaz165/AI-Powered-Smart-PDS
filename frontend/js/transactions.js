/**
 * AI-Powered Smart PDS - Transactions Controller
 */

let allTransactions = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadTransactions();

  document.getElementById('new-txn-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-txn');
    const benId = document.getElementById('txn-ben-id').value.trim();
    const commodity = document.getElementById('txn-commodity').value;
    const region = document.getElementById('txn-region').value;
    const qty = parseFloat(document.getElementById('txn-qty').value);

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

    try {
      const res = await API.distributeGrain({
        beneficiary_id: benId,
        commodity: commodity,
        quantity: qty,
        region: region,
        ration_shop_id: `FPS-${region.substring(0,3).toUpperCase()}-001`
      });

      if (res && res.status === 'success') {
        const d = res.data;
        if (d.status === 'SUSPICIOUS') {
          showToast(`Transaction ${d.transaction_id} recorded but FLAGGED for review: ${d.reason}`, 'warning');
        } else {
          showToast(`Transaction ${d.transaction_id} successful! Deducted ${qty} kg. Remaining stock: ${d.remaining_stock} kg.`, 'success');
        }
        closeModal('new-txn-modal');
        document.getElementById('new-txn-form').reset();
        await loadTransactions();
      }
    } catch (err) {
      showToast(err.message || 'Transaction rejected by server', 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-check"></i> Authorize & Distribute';
    }
  });
});

async function loadTransactions() {
  try {
    const res = await API.getTransactions({ limit: 100 });
    if (res && res.status === 'success') {
      allTransactions = res.data;
      renderTransactionsTable(allTransactions);
    }
  } catch (err) {
    showToast('Failed to load transactions', 'error');
  }
}

function renderTransactionsTable(txns) {
  const tbody = document.getElementById('txns-tbody');
  if (!tbody) return;

  if (!txns || txns.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">No grain distribution transactions found.</td></tr>';
    return;
  }

  tbody.innerHTML = txns.map(t => {
    let badgeClass = 'badge-success';
    if (t.risk_level === 'HIGH' || t.status === 'SUSPICIOUS') {
      badgeClass = 'badge-danger';
    } else if (t.risk_level === 'MEDIUM') {
      badgeClass = 'badge-warning';
    }

    const timeStr = t.timestamp ? new Date(t.timestamp).toLocaleDateString() + ' ' + new Date(t.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : 'Recent';

    return `
      <tr>
        <td><strong>${t.transaction_id}</strong></td>
        <td>${t.beneficiary_id}</td>
        <td><span class="badge badge-info">${t.commodity}</span></td>
        <td><strong>${t.quantity} kg</strong></td>
        <td>${t.ration_shop_id || '-'}</td>
        <td>${t.region || 'Chennai'}</td>
        <td style="font-size:0.8rem; color:var(--text-muted);">${timeStr}</td>
        <td><span class="badge ${badgeClass}">${t.status} (${t.risk_level || 'LOW'})</span></td>
        <td style="max-width: 250px; font-size: 0.8rem; color: var(--text-secondary);">${t.reason || 'Normal entitlement distribution'}</td>
      </tr>
    `;
  }).join('');
}

function filterTransactions() {
  const search = document.getElementById('txn-search').value.toLowerCase();
  const status = document.getElementById('txn-filter-status').value;
  const commodity = document.getElementById('txn-filter-commodity').value;

  const filtered = allTransactions.filter(t => {
    const matchSearch = t.transaction_id.toLowerCase().includes(search) || t.beneficiary_id.toLowerCase().includes(search);
    const matchStatus = !status || t.status === status;
    const matchCom = !commodity || t.commodity === commodity;
    return matchSearch && matchStatus && matchCom;
  });

  renderTransactionsTable(filtered);
}
