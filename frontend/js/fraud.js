/**
 * AI-Powered Smart PDS - Fraud & Anomaly Controller
 */

let currentAlerts = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadFraudAlerts();

  // Review Form Submission Handler
  const reviewForm = document.getElementById('review-fraud-form');
  if (reviewForm) {
    reviewForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await submitOfficialReview();
    });
  }

  // Live Simulator Form Handler
  const simForm = document.getElementById('simulate-anomaly-form');
  if (simForm) {
    simForm.addEventListener('submit', async (e) => {
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
            document.getElementById('sim-res-risk').className = d.risk_level === 'HIGH' ? 'badge badge-danger' : 'badge badge-warning';
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
          document.getElementById('sim-res-score').textContent = `Isolation Forest Score: ${d.anomaly_score} | Entitled Quota: ${d.entitled_quota} kg (Ratio: ${d.quantity_to_quota_ratio}x)`;
          const interpEl = document.getElementById('sim-res-interp');
          if (interpEl) {
            interpEl.textContent = `Interpretation: ${d.score_interpretation || 'Unsupervised isolation score'}`;
          }
        }
      } catch (err) {
        showToast(err.message || 'Anomaly scan error', 'error');
      }
    });
  }
});

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(String(str)));
  return div.innerHTML;
}

async function loadFraudAlerts() {
  const region = document.getElementById('filter-fraud-region')?.value || 'ALL';
  const risk = document.getElementById('filter-fraud-risk')?.value || 'ALL';
  const status = document.getElementById('filter-fraud-status')?.value || 'ALL';

  const params = {};
  if (region !== 'ALL') params.region = region;
  if (risk !== 'ALL') params.risk_level = risk;
  if (status !== 'ALL') params.status = status;

  try {
    const res = await API.getFraudAlerts(params);
    const tbody = document.getElementById('fraud-alerts-tbody');
    const totalBadge = document.getElementById('fraud-total-badge');
    const pendingBadge = document.getElementById('fraud-pending-badge');
    if (!tbody) return;

    if (res && res.status === 'success') {
      currentAlerts = res.data || [];
      if (totalBadge) totalBadge.textContent = `${res.total || currentAlerts.length} Total Records`;
      if (pendingBadge) pendingBadge.textContent = `${res.pending_count || 0} Pending Review`;

      if (currentAlerts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--text-muted); padding:24px;">No flagged transactions matching current filter criteria.</td></tr>';
        return;
      }

      tbody.innerHTML = currentAlerts.map(a => {
        const isHigh = a.risk_level === 'HIGH';
        const isPending = a.status === 'PENDING_REVIEW' || !a.status;
        const score = typeof a.anomaly_score === 'number' ? a.anomaly_score.toFixed(4) : (a.anomaly_score || '-0.2500');
        
        let decisionBadge = '<span class="badge badge-warning"><i class="fa-solid fa-clock"></i> Pending Review</span>';
        if (a.review_decision === 'VERIFIED_LEGITIMATE' || a.status === 'VERIFIED_LEGITIMATE' || a.review_decision === 'APPROVED_GENUINE') {
          decisionBadge = '<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> Verified Legitimate</span>';
        } else if (a.review_decision === 'CONFIRMED_IRREGULARITY' || a.status === 'CONFIRMED_IRREGULARITY' || a.review_decision === 'FLAGGED_FRAUD') {
          decisionBadge = '<span class="badge badge-danger"><i class="fa-solid fa-ban"></i> Confirmed Irregularity</span>';
        } else if (a.review_decision === 'DISMISSED_FALSE_POSITIVE') {
          decisionBadge = '<span class="badge badge-secondary"><i class="fa-solid fa-circle-xmark"></i> False Positive</span>';
        } else if (a.review_decision === 'REQUIRES_INSPECTION') {
          decisionBadge = '<span class="badge badge-purple"><i class="fa-solid fa-magnifying-glass"></i> Field Inspection</span>';
        } else if (a.status === 'RESOLVED') {
          decisionBadge = '<span class="badge badge-success"><i class="fa-solid fa-check"></i> Resolved</span>';
        }

        const scoreBadgeClass = a.score_badge === 'SEVERE_ANOMALY' ? 'badge-danger' : (a.score_badge === 'MILD_ANOMALY' ? 'badge-warning' : 'badge-secondary');
        const scoreInterp = a.score_interpretation || (Number(score) < 0 ? 'Statistical Outlier (<0)' : 'Normal Inlier (>=0)');
        const dtStr = a.created_at_formatted || (a.created_at ? new Date(a.created_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '');

        return `
          <tr>
            <td>
              <span class="txn-code-pill">${escapeHtml(a.transaction_id)}</span>
              ${dtStr ? `<div style="font-size:0.68rem; color:var(--text-muted); margin-top:2px;"><i class="fa-regular fa-clock"></i> ${escapeHtml(dtStr)}</div>` : ''}
            </td>
            <td>
              <span class="ben-code-pill">${escapeHtml(a.beneficiary_id)}</span>
            </td>
            <td>
              <span class="badge badge-info">${escapeHtml(a.commodity)}</span>
              <strong style="margin-left:4px; color:#fff; font-size:0.85rem;">${escapeHtml(a.quantity)} kg</strong>
              ${a.entitled_quota ? `<div style="font-size:0.68rem; color:var(--text-muted); margin-top:1px;">Quota: ${a.entitled_quota} kg ${a.quantity_to_quota_ratio ? `(${a.quantity_to_quota_ratio}x)` : ''}</div>` : ''}
            </td>
            <td>${escapeHtml(a.region || 'Chennai')}</td>
            <td><span class="badge ${isHigh ? 'badge-danger' : 'badge-warning'}">${escapeHtml(a.risk_level)}</span></td>
            <td>
              <div style="font-family:monospace; font-weight:700; color:${Number(score) < 0 ? 'var(--accent-rose)' : 'var(--accent-emerald)'}; font-size:0.86rem;">${score}</div>
              <span class="badge ${scoreBadgeClass}" style="font-size:0.65rem; margin-top:2px;" title="${escapeHtml(scoreInterp)}">
                ${Number(score) < 0 ? '<i class="fa-solid fa-triangle-exclamation"></i> Outlier (&lt;0)' : '<i class="fa-solid fa-check"></i> Inlier (&ge;0)'}
              </span>
            </td>
            <td style="max-width: 260px; font-size: 0.76rem; color: #fecdd3; line-height:1.35;">${escapeHtml(a.reason)}</td>
            <td>
              ${decisionBadge}
              ${a.reviewed_by ? `<div style="font-size:0.68rem; color:var(--text-muted); margin-top:2px;"><i class="fa-solid fa-user-check"></i> ${escapeHtml(a.reviewed_by)}</div>` : ''}
            </td>
            <td class="col-actions">
              <button class="btn btn-secondary btn-sm" onclick="openReviewModal('${escapeHtml(a.transaction_id)}')" style="white-space:nowrap; padding:5px 10px; font-size:0.75rem;">
                <i class="fa-solid fa-gavel"></i> ${isPending ? 'Audit &amp; Review' : 'Update Review'}
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    showToast('Failed to load fraud alerts from server', 'error');
  }
}

function openReviewModal(txnId) {
  const alert = currentAlerts.find(a => a.transaction_id === txnId);
  if (!alert) {
    showToast(`Alert record for ${txnId} not found`, 'error');
    return;
  }

  document.getElementById('rev-txn-id').value = alert.transaction_id;
  document.getElementById('rev-modal-txn-title').textContent = `${alert.transaction_id} (${alert.commodity})`;
  
  const riskBadge = document.getElementById('rev-modal-risk-badge');
  if (riskBadge) {
    riskBadge.className = alert.risk_level === 'HIGH' ? 'badge badge-danger' : 'badge badge-warning';
    riskBadge.textContent = `${alert.risk_level} RISK`;
  }

  document.getElementById('rev-modal-ben').textContent = alert.beneficiary_id;
  document.getElementById('rev-modal-region').textContent = alert.region || 'Chennai';
  document.getElementById('rev-modal-commodity').textContent = alert.commodity;
  document.getElementById('rev-modal-quantity').textContent = `${alert.quantity} kg`;
  document.getElementById('rev-modal-quota').textContent = alert.entitled_quota ? `${alert.entitled_quota} kg` : 'N/A';
  
  const timeEl = document.getElementById('rev-modal-time');
  if (timeEl) {
    timeEl.textContent = alert.created_at_formatted || (alert.created_at ? new Date(alert.created_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : 'Recorded Alert');
  }

  const scoreVal = typeof alert.anomaly_score === 'number' ? alert.anomaly_score.toFixed(4) : (alert.anomaly_score || '-0.2500');
  document.getElementById('rev-modal-score').textContent = scoreVal;
  document.getElementById('rev-modal-score-interp').textContent = alert.score_interpretation || (Number(scoreVal) < 0 ? 'Statistical Outlier (Short tree isolation path)' : 'Normal Inlier');
  document.getElementById('rev-modal-reason').textContent = `ML Flag: ${alert.reason}`;

  // Default values
  const storedUser = sessionStorage.getItem('user_name') || 'OFFICER-CHN-01';
  document.getElementById('rev-officer-id').value = alert.reviewed_by || storedUser;
  document.getElementById('rev-decision').value = alert.review_decision || alert.status || 'VERIFIED_LEGITIMATE';
  document.getElementById('rev-reason').value = alert.review_reason || alert.comments || '';

  // Render past review audit history trail
  const histContainer = document.getElementById('rev-modal-history-container');
  const histList = document.getElementById('rev-modal-history-list');
  if (histContainer && histList) {
    const history = alert.review_history || [];
    if (history.length > 0) {
      histContainer.style.display = 'block';
      histList.innerHTML = history.map(h => {
        const hTime = h.reviewed_at ? new Date(h.reviewed_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : 'Logged';
        return `
          <div style="padding: 4px 0; border-bottom: 1px dashed rgba(255,255,255,0.08);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="color:var(--accent-amber);">${escapeHtml(h.decision)}</strong>
              <span style="font-size:0.68rem; color:var(--text-muted);">${escapeHtml(hTime)}</span>
            </div>
            <div style="font-size:0.71rem; color:var(--text-secondary); margin-top:1px;">
              Officer: <code>${escapeHtml(h.officer_id)}</code> &bull; <em>"${escapeHtml(h.reason || h.comments || 'No comments')}"</em>
            </div>
          </div>
        `;
      }).join('');
    } else {
      histContainer.style.display = 'none';
      histList.innerHTML = '';
    }
  }

  openModal('review-fraud-modal');
}

async function submitOfficialReview() {
  const btn = document.getElementById('btn-submit-review');
  const txnId = document.getElementById('rev-txn-id').value;
  const officerId = document.getElementById('rev-officer-id').value.trim();
  const decision = document.getElementById('rev-decision').value;
  const reason = document.getElementById('rev-reason').value.trim();

  if (!officerId) {
    showToast('Officer ID is required.', 'error');
    return;
  }
  if (!reason || reason.length < 3) {
    showToast('Please provide an official audit reason / written comments (min 3 chars).', 'error');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Recording Decision...';
  }

  try {
    const res = await API.reviewFraudAlert(txnId, {
      officer_id: officerId,
      decision: decision,
      reason: reason,
      comments: reason
    });

    if (res && res.status === 'success') {
      showToast(`Audit decision recorded for ${txnId}: ${decision}`, 'success');
      closeModal('review-fraud-modal');
      await loadFraudAlerts();
    } else {
      showToast(res.message || 'Failed to submit review', 'error');
    }
  } catch (err) {
    showToast(err.message || 'Error recording audit review decision', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-stamp"></i> Record Official Decision';
    }
  }
}
    showToast('Please provide an official audit reason (min 3 chars).', 'error');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Recording Decision...';
  }

  try {
    const res = await API.reviewFraudAlert(txnId, {
      officer_id: officerId,
      decision: decision,
      reason: reason
    });

    if (res && res.status === 'success') {
      showToast(`Audit decision recorded for ${txnId}: ${decision}`, 'success');
      closeModal('review-fraud-modal');
      await loadFraudAlerts();
    } else {
      showToast(res.message || 'Failed to submit review', 'error');
    }
  } catch (err) {
    showToast(err.message || 'Error recording audit review decision', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-stamp"></i> Record Official Decision';
    }
  }
}

function resetFraudFilters() {
  const reg = document.getElementById('filter-fraud-region');
  const rsk = document.getElementById('filter-fraud-risk');
  const sts = document.getElementById('filter-fraud-status');

  if (reg) reg.value = 'ALL';
  if (rsk) rsk.value = 'ALL';
  if (sts) sts.value = 'PENDING_REVIEW';

  loadFraudAlerts();
  showToast('Filters reset', 'info');
}
