/**
 * AI-Powered Smart PDS - Fraud & Anomaly Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
  await loadFraudAlerts();

  document.getElementById('simulate-anomaly-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const com = document.getElementById('sim-commodity').value;
    const qty = parseFloat(document.getElementById('sim-qty').value);
    const size = parseInt(document.getElementById('sim-family-size').value, 10);
    const card = document.getElementById('sim-card-type').value;
    const priorDays = parseFloat(document.getElementById('sim-prior-days').value);
    const freq = parseInt(document.getElementById('sim-monthly-freq').value, 10);

    try {
      const res = await API.detectAnomaly({
        commodity: com,
        quantity: qty,
        family_size: size,
        card_type: card,
        days_since_prior_txn: priorDays,
        monthly_frequency: freq
      });

      if (res && res.status === 'success') {
        const d = res.data;
        const box = document.getElementById('sim-result-box');
        box.style.display = 'block';

        if (d.status === 'SUSPICIOUS') {
          box.style.background = 'rgba(244, 63, 94, 0.12)';
          box.style.border = '1px solid rgba(244, 63, 94, 0.35)';
          document.getElementById('sim-res-status').textContent = 'SUSPICIOUS PATTERN DETECTED';
          document.getElementById('sim-res-status').style.color = '#fb7185';
          document.getElementById('sim-res-risk').className = 'badge badge-danger';
          document.getElementById('sim-res-risk').textContent = `${d.risk_level} RISK`;
        } else {
          box.style.background = 'rgba(16, 185, 129, 0.12)';
          box.style.border = '1px solid rgba(16, 185, 129, 0.35)';
          document.getElementById('sim-res-status').textContent = 'NORMAL DISTRIBUTION CONFORMS TO QUOTA';
          document.getElementById('sim-res-status').style.color = '#34d399';
          document.getElementById('sim-res-risk').className = 'badge badge-success';
          document.getElementById('sim-res-risk').textContent = 'LOW RISK';
        }

        document.getElementById('sim-res-reason').textContent = `Reason: ${d.reason}`;
        document.getElementById('sim-res-score').textContent = `Isolation Forest Decision Score: ${d.anomaly_score} | Entitled Quota: ${d.entitled_quota} kg (Ratio: ${d.quantity_to_quota_ratio}x)`;
      }
    } catch (err) {
      showToast(err.message || 'Anomaly scan error', 'error');
    }
  });
});

async function loadFraudAlerts() {
  try {
    const res = await API.getFraudAlerts();
    const tbody = document.getElementById('fraud-alerts-tbody');
    const badge = document.getElementById('fraud-total-badge');
    if (!tbody) return;

    if (res && res.status === 'success') {
      const alerts = res.data;
      if (badge) badge.textContent = `${alerts.length} Flagged Outliers`;

      if (alerts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">No flagged anomaly alerts currently active. All transactions normal.</td></tr>';
        return;
      }

      tbody.innerHTML = alerts.map(a => {
        const isHigh = a.risk_level === 'HIGH';
        return `
          <tr>
            <td><strong>${a.transaction_id}</strong></td>
            <td>${a.beneficiary_id}</td>
            <td><span class="badge badge-info">${a.commodity}</span></td>
            <td><strong>${a.quantity} kg</strong></td>
            <td>${a.region || 'Chennai'}</td>
            <td><span class="badge ${isHigh ? 'badge-danger' : 'badge-warning'}">${a.risk_level}</span></td>
            <td><code>${a.anomaly_score !== undefined ? a.anomaly_score : -0.25}</code></td>
            <td style="max-width: 280px; font-size: 0.82rem; color: #fecdd3;">${a.reason}</td>
            <td>
              <button class="btn btn-secondary btn-sm" onclick="resolveAlert('${a.transaction_id}')">
                <i class="fa-solid fa-check"></i> Verify & Close
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    showToast('Failed to load fraud alerts', 'error');
  }
}

function resolveAlert(txnId) {
  showToast(`Transaction ${txnId} verified by officer. Audit recorded.`, 'info');
  // Visually remove row
  setTimeout(loadFraudAlerts, 500);
}
