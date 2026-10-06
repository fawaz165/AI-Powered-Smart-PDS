/**
 * AI-Powered Smart PDS - Predictions Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
  await loadModelMetrics();
  // Trigger initial demo forecast
  executeDemandForecast();

  document.getElementById('demand-forecast-form').addEventListener('submit', (e) => {
    e.preventDefault();
    executeDemandForecast();
  });
});

async function loadModelMetrics() {
  try {
    const res = await API.getModelMetrics();
    const tbody = document.getElementById('metrics-tbody');
    if (!tbody) return;

    if (res && res.status === 'success' && res.data.evaluation_metrics) {
      const bestName = res.data.best_model;
      const metrics = res.data.evaluation_metrics;

      tbody.innerHTML = Object.keys(metrics).map(name => {
        const m = metrics[name];
        const isBest = name === bestName;
        return `
          <tr style="${isBest ? 'background: rgba(59, 130, 246, 0.08); font-weight: 600;' : ''}">
            <td>
              <strong>${name}</strong>
              ${isBest ? ' <span class="badge badge-success" style="font-size:0.68rem; margin-left:6px;"><i class="fa-solid fa-crown"></i> Best Selected</span>' : ''}
            </td>
            <td>${m.MAE.toFixed(2)} kg</td>
            <td>${m.MSE.toLocaleString()}</td>
            <td>${m.RMSE.toFixed(2)} kg</td>
            <td><strong style="color:var(--accent-emerald);">${(m.R2 * 100).toFixed(2)}% (${m.R2.toFixed(4)})</strong></td>
            <td>${isBest ? '<span class="badge badge-info">Active in Production API</span>' : '<span class="badge badge-secondary" style="background:rgba(255,255,255,0.05); color:#94a3b8;">Benchmarked</span>'}</td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    console.error('Failed to load metrics:', err);
  }
}

async function executeDemandForecast() {
  const btn = document.getElementById('btn-predict-demand');
  const commodity = document.getElementById('pred-commodity').value;
  const region = document.getElementById('pred-region').value;
  const month = parseInt(document.getElementById('pred-month').value, 10);
  const benCount = parseInt(document.getElementById('pred-beneficiaries').value, 10);
  const currentStock = parseFloat(document.getElementById('pred-stock').value);
  const prevDemand = parseFloat(document.getElementById('pred-prev-demand').value);

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running ML Inference...';
  }

  try {
    const res = await API.predictDemand({
      commodity: commodity,
      region: region,
      month: month,
      beneficiary_count: benCount,
      current_stock: currentStock,
      previous_demand: prevDemand
    });

    if (res && res.status === 'success') {
      const d = res.data;
      document.getElementById('res-predicted-demand').innerHTML = `${Math.round(d.predicted_demand).toLocaleString()} <span style="font-size:1.2rem; color:var(--text-secondary); font-weight:500;">kg</span>`;
      document.getElementById('res-current-stock').textContent = `${Math.round(d.current_stock).toLocaleString()} kg`;
      document.getElementById('res-shortage').textContent = `${Math.round(d.shortage).toLocaleString()} kg`;
      document.getElementById('res-procurement').textContent = `${Math.round(d.recommended_procurement).toLocaleString()} kg`;

      const badge = document.getElementById('res-status-badge');
      const msgBox = document.getElementById('res-ai-message');

      if (d.status === 'SHORTAGE') {
        badge.className = 'badge badge-danger';
        badge.textContent = 'Potential Shortage';
        msgBox.style.background = 'rgba(244, 63, 94, 0.12)';
        msgBox.style.borderColor = 'rgba(244, 63, 94, 0.35)';
        msgBox.style.color = '#fecdd3';
        msgBox.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Potential shortage: ${Math.round(d.shortage)} kg. Recommended procurement: ${Math.round(d.recommended_procurement)} kg.`;
      } else if (d.status === 'EXCESS') {
        badge.className = 'badge badge-purple';
        badge.textContent = 'Excess Inventory';
        msgBox.style.background = 'rgba(139, 92, 246, 0.12)';
        msgBox.style.borderColor = 'rgba(139, 92, 246, 0.35)';
        msgBox.style.color = '#ddd6fe';
        msgBox.innerHTML = `<i class="fa-solid fa-boxes-packing"></i> ${d.message}`;
      } else {
        badge.className = 'badge badge-success';
        badge.textContent = 'Stock Sufficient';
        msgBox.style.background = 'rgba(16, 185, 129, 0.12)';
        msgBox.style.borderColor = 'rgba(16, 185, 129, 0.35)';
        msgBox.style.color = '#a7f3d0';
        msgBox.innerHTML = `<i class="fa-solid fa-circle-check"></i> Stock is sufficient to satisfy anticipated monthly beneficiary demand.`;
      }

      showToast(`Prediction generated: ${Math.round(d.predicted_demand)} kg for ${commodity}`, 'success');
    }
  } catch (err) {
    showToast(err.message || 'Demand forecast failed', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-microchip"></i> Execute ML Demand Prediction';
    }
  }
}

function fillProjectExample() {
  // Sets exact parameters from prompt Section 1:
  // Current stock = 3,800 kg, Predicted demand will be ~4,500 kg, Shortage = 700 kg
  document.getElementById('pred-commodity').value = 'Rice';
  document.getElementById('pred-region').value = 'Chennai';
  document.getElementById('pred-month').value = '11';
  document.getElementById('pred-beneficiaries').value = '12500';
  document.getElementById('pred-stock').value = '3800';
  document.getElementById('pred-prev-demand').value = '4200';
  executeDemandForecast();
}
