/**
 * AI-Powered Smart PDS - Demand Forecast Workbench Controller
 */

let isCustomScenario = false;
let liveDbStock = 3800;
let liveDbBenCount = 12500;
let liveDbBuffer = 500;

document.addEventListener('DOMContentLoaded', async () => {
  await populateCommoditiesDropdown();
  await loadModelMetrics();
  // Sync initial live DB values for default commodity & region
  await syncDatabaseValues();
  // Trigger initial forecast
  await executeDemandForecast();

  const form = document.getElementById('demand-forecast-form');
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      executeDemandForecast();
    });
  }
});

/** XSS-safe escaping */
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(String(str)));
  return div.innerHTML;
}

async function populateCommoditiesDropdown() {
  const select = document.getElementById('pred-commodity');
  if (!select) return;
  try {
    const res = await API.getCommodities();
    if (res && res.status === 'success' && res.data && res.data.length > 0) {
      const cur = select.value;
      select.innerHTML = res.data.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.commodity_code)})</option>`).join('');
      if (cur && res.data.some(c => c.name === cur)) {
        select.value = cur;
      }
    }
  } catch (err) {
    console.warn('Could not populate commodities dynamically, using defaults:', err);
  }
}

/** Synchronizes live stock, buffer, and beneficiary count directly from the MongoDB collections */
async function syncDatabaseValues() {
  const commodity = document.getElementById('pred-commodity').value;
  const region = document.getElementById('pred-region').value;

  try {
    // 1. Fetch live stock from Inventory API
    const invRes = await API.getInventory({ commodity, region });
    if (invRes && invRes.status === 'success' && invRes.data && invRes.data.length > 0) {
      const item = invRes.data[0];
      liveDbStock = parseFloat(item.current_stock) || 0;
      liveDbBuffer = parseFloat(item.buffer_stock) || 500;
      document.getElementById('pred-stock').value = liveDbStock;
      document.getElementById('pred-safety-stock').value = liveDbBuffer;

      const stockBadge = document.getElementById('badge-stock');
      if (stockBadge) {
        stockBadge.className = 'badge badge-info';
        stockBadge.innerHTML = `<i class="fa-solid fa-database"></i> Live DB (${liveDbStock.toLocaleString()} kg)`;
      }

      const bufferBadge = document.getElementById('badge-safety-stock');
      if (bufferBadge) {
        bufferBadge.className = 'badge badge-info';
        bufferBadge.innerHTML = `<i class="fa-solid fa-database"></i> DB Buffer (${liveDbBuffer.toLocaleString()} kg)`;
      }

      const stockLabel = document.getElementById('stock-source-label');
      if (stockLabel) stockLabel.innerHTML = `<span style="color:var(--accent-cyan);">Live depot stock in ${escapeHtml(region)}</span>`;
    }

    // 2. Fetch live beneficiary count from Beneficiaries API
    const benRes = await API.getBeneficiaries({ region, limit: 1000 });
    if (benRes && benRes.status === 'success') {
      const rawCount = benRes.total !== undefined ? benRes.total : (benRes.data ? benRes.data.length : 12500);
      liveDbBenCount = rawCount >= 100 ? rawCount : 12500;
      document.getElementById('pred-beneficiaries').value = liveDbBenCount;

      const benBadge = document.getElementById('badge-ben');
      if (benBadge) {
        benBadge.className = 'badge badge-info';
        benBadge.innerHTML = `<i class="fa-solid fa-database"></i> Live DB (${liveDbBenCount.toLocaleString()} cards)`;
      }

      const benLabel = document.getElementById('ben-source-label');
      if (benLabel) {
        benLabel.innerHTML = rawCount < 100 
          ? `<span style="color:var(--accent-cyan);">${rawCount} sample cards in DB &bull; Operational depot scale: 12,500</span>`
          : `<span style="color:var(--accent-cyan);">Live registered cardholders in ${escapeHtml(region)}</span>`;
      }
    }

    isCustomScenario = false;
    updateSourceBadges(false);
    showToast(`Synchronized live database values for ${commodity} in ${region}`, 'info');
  } catch (err) {
    console.warn('Could not sync live DB values:', err);
  }
}

function onParameterChange() {
  if (!isCustomScenario) {
    syncDatabaseValues();
  }
}

function onFieldManualEdit(fieldName) {
  isCustomScenario = true;
  updateSourceBadges(true);

  if (fieldName === 'ben') {
    const b = document.getElementById('badge-ben');
    if (b) { b.className = 'badge badge-warning'; b.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario Value'; }
    const lbl = document.getElementById('ben-source-label');
    if (lbl) lbl.innerHTML = '<span style="color:var(--accent-amber);">Manually customized scenario count</span>';
  } else if (fieldName === 'stock') {
    const b = document.getElementById('badge-stock');
    if (b) { b.className = 'badge badge-warning'; b.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario Value'; }
    const lbl = document.getElementById('stock-source-label');
    if (lbl) lbl.innerHTML = '<span style="color:var(--accent-amber);">Manually customized warehouse balance</span>';
  } else if (fieldName === 'safety-stock') {
    const b = document.getElementById('badge-safety-stock');
    if (b) { b.className = 'badge badge-warning'; b.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario Value'; }
  } else if (fieldName === 'prev-demand') {
    const b = document.getElementById('badge-prev-demand');
    if (b) { b.className = 'badge badge-warning'; b.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario Value'; }
  }
}

function updateSourceBadges(isCustom) {
  const formBadge = document.getElementById('form-source-badge');
  const resBadge = document.getElementById('res-source-badge');

  if (formBadge) {
    if (isCustom) {
      formBadge.className = 'badge badge-warning';
      formBadge.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Manual Scenario Values';
    } else {
      formBadge.className = 'badge badge-info';
      formBadge.innerHTML = '<i class="fa-solid fa-database"></i> Live Database Values';
    }
  }

  if (resBadge) {
    if (isCustom) {
      resBadge.className = 'badge badge-warning';
      resBadge.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Manual Scenario';
    } else {
      resBadge.className = 'badge badge-info';
      resBadge.innerHTML = '<i class="fa-solid fa-database"></i> Live DB Values';
    }
  }
}

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
              <strong>${escapeHtml(name)}</strong>
              ${isBest ? ' <span class="badge badge-success" style="font-size:0.68rem; margin-left:6px;"><i class="fa-solid fa-crown"></i> Benchmark Winner</span>' : ''}
            </td>
            <td>${Number(m.MAE).toFixed(2)} kg</td>
            <td>${Number(m.MSE).toLocaleString()}</td>
            <td>${Number(m.RMSE).toFixed(2)} kg</td>
            <td><strong style="color:var(--accent-emerald); font-family:monospace;">${Number(m.R2).toFixed(4)}</strong></td>
            <td>${isBest ? '<span class="badge badge-info">Active in Production</span>' : '<span class="badge badge-secondary" style="background:rgba(255,255,255,0.05); color:#94a3b8;">Benchmarked</span>'}</td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    console.error('Failed to load model metrics:', err);
  }
}

async function executeDemandForecast() {
  const btn = document.getElementById('btn-predict-demand');
  const commodity = document.getElementById('pred-commodity').value;
  const region = document.getElementById('pred-region').value;
  const month = parseInt(document.getElementById('pred-month').value, 10);
  const year = parseInt(document.getElementById('pred-year').value, 10);
  const benCount = parseInt(document.getElementById('pred-beneficiaries').value, 10);
  const currentStock = parseFloat(document.getElementById('pred-stock').value);
  const prevDemand = parseFloat(document.getElementById('pred-prev-demand').value);
  const safetyStock = parseFloat(document.getElementById('pred-safety-stock').value) || 0;

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Calculating ML Forecast...';
  }

  try {
    const res = await API.predictDemand({
      commodity: commodity,
      region: region,
      month: month,
      year: year,
      beneficiary_count: benCount,
      current_stock: currentStock,
      previous_demand: prevDemand,
      safety_stock: safetyStock,
      is_custom_scenario: isCustomScenario
    });

    if (res && res.status === 'success') {
      const d = res.data;
      
      // 1. KPI Numbers
      document.getElementById('res-predicted-demand').innerHTML = `${Math.round(d.predicted_demand).toLocaleString()} <span style="font-size:1.1rem; color:var(--text-secondary); font-weight:500;">kg</span>`;
      document.getElementById('res-current-stock').textContent = `${Math.round(d.current_stock).toLocaleString()} kg`;
      document.getElementById('res-safety-stock').textContent = `${Math.round(d.safety_stock || 0).toLocaleString()} kg`;
      document.getElementById('res-shortage').textContent = `${Math.round(d.shortage).toLocaleString()} kg`;
      document.getElementById('res-procurement').textContent = `${Math.round(d.recommended_procurement).toLocaleString()} kg`;

      // 2. Model & Validation Info
      const modelInfoEl = document.getElementById('res-model-info');
      if (modelInfoEl) {
        modelInfoEl.innerHTML = `<i class="fa-solid fa-circle-check" style="color:var(--accent-emerald);"></i> Pipeline Model: <strong>${escapeHtml(d.model_used || 'Linear Regression')}</strong> • Benchmark Validated`;
      }

      // 3. Status and Data Source Badges
      const statusBadge = document.getElementById('res-status-badge');
      updateSourceBadges(d.data_source === 'USER_SCENARIO' || isCustomScenario);

      if (statusBadge) {
        if (d.status === 'SHORTAGE') {
          statusBadge.className = 'badge badge-danger';
          statusBadge.textContent = 'Potential Shortage';
        } else if (d.status === 'EXCESS') {
          statusBadge.className = 'badge badge-purple';
          statusBadge.textContent = 'Excess Stock';
        } else {
          statusBadge.className = 'badge badge-success';
          statusBadge.textContent = 'Stock Optimal';
        }
      }

      // 4. Explainability & Factor Analysis
      const explanation = d.explanation || {};
      const summaryEl = document.getElementById('res-explanation-summary');
      if (summaryEl) {
        summaryEl.textContent = explanation.summary || d.message || 'Forecast generated from demographic, lag, and seasonal pipeline features.';
      }

      const factorsGrid = document.getElementById('res-factors-grid');
      if (factorsGrid && explanation.factors) {
        factorsGrid.innerHTML = explanation.factors.map(f => `
          <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 8px 10px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
              <span style="font-size:0.75rem; font-weight:600; color:var(--text-primary);">${escapeHtml(f.name)}</span>
              <span class="badge ${f.impact.includes('+') || f.impact === 'Primary (+)' ? 'badge-info' : (f.impact === 'Deficit' ? 'badge-danger' : 'badge-secondary')}" style="font-size:0.65rem; padding:2px 6px;">
                ${escapeHtml(f.impact)}
              </span>
            </div>
            <div style="font-size:0.8rem; font-weight:600; color:var(--accent-cyan); margin-bottom:2px;">${escapeHtml(f.value)}</div>
            <div style="font-size:0.72rem; color:var(--text-muted); line-height:1.3;">${escapeHtml(f.detail)}</div>
          </div>
        `).join('');
      }

      // 5. Mathematical Calculation Breakdown
      const bd = d.calculation_breakdown || {};
      const breakdownEl = document.getElementById('res-calculation-breakdown');
      if (breakdownEl) {
        const rawPred = Math.round(bd.raw_pipeline_prediction || d.predicted_demand).toLocaleString();
        const finalDemand = Math.round(d.predicted_demand).toLocaleString();
        const baseDemand = Math.round(bd.baseline_demand || 4200).toLocaleString();
        const baseMom = Math.round(bd.baseline_momentum_kg || (bd.baseline_demand * 0.9927)).toLocaleString();
        const stockVal = Math.round(d.current_stock).toLocaleString();
        const bufferVal = Math.round(d.safety_stock || 0).toLocaleString();
        const grossVal = Math.round((d.predicted_demand || 0) + (d.safety_stock || 0)).toLocaleString();
        const shortageVal = Math.round(d.shortage).toLocaleString();
        const procureVal = Math.round(d.recommended_procurement).toLocaleString();
        const seasonalIdx = (bd.seasonal_multiplier || 1.0).toFixed(2);
        const seasonalLbl = bd.seasonal_label || 'Standard Baseline';
        const trendText = bd.annual_trend_factor > 1.0 ? ` &times; ${bd.annual_trend_factor.toFixed(2)} (${d.year} forward trend)` : '';

        breakdownEl.innerHTML = `
          <div style="margin-bottom:3px;">&bull; <strong>1. Baseline Momentum:</strong> Historical baseline ${baseDemand} kg &rarr; quota &amp; consumption scaling &asymp; <strong style="color:var(--text-primary);">${baseMom} kg</strong></div>
          <div style="margin-bottom:3px;">&bull; <strong>2. Seasonal &amp; Calendar Multiplier:</strong> ${seasonalIdx}x (${escapeHtml(seasonalLbl)}) applied to festival/climatic demand profile</div>
          <div style="margin-bottom:3px;">&bull; <strong>3. Pipeline Inference &rarr; Base Model:</strong> Demographics + Lag + Seasonal features &rarr; <strong style="color:var(--accent-cyan);">${rawPred} kg</strong></div>
          <div style="margin-bottom:3px;">&bull; <strong>4. Final Predicted Demand:</strong> Base Prediction (${rawPred} kg)${trendText} &rarr; <strong style="color:#fff; font-size:0.82rem;">${finalDemand} kg</strong></div>
          <div style="margin-bottom:3px;">&bull; <strong>5. Gross Requirement:</strong> Predicted Demand (${finalDemand} kg) + Safety Buffer (${bufferVal} kg) = <strong style="color:var(--accent-cyan);">${grossVal} kg</strong></div>
          <div style="margin-bottom:3px;">&bull; <strong>6. Net Shortage:</strong> max(0, Demand [${finalDemand}] &minus; Warehouse Stock [${stockVal}]) = <strong style="color:var(--accent-rose);">${shortageVal} kg</strong></div>
          <div>&bull; <strong>7. Procurement Recommended:</strong> max(0, Gross Need [${grossVal}] &minus; Warehouse Stock [${stockVal}]) = <strong style="color:var(--accent-amber); font-weight:700;">${procureVal} kg</strong></div>
        `;
      }

      showToast(`Calculated demand: ${Math.round(d.predicted_demand).toLocaleString()} kg for ${commodity} in ${region}`, 'success');
    }
  } catch (err) {
    showToast(err.message || 'Demand forecast failed', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-microchip"></i> Calculate Demand & Procurement';
    }
  }
}

function fillProjectExample() {
  document.getElementById('pred-commodity').value = 'Rice';
  document.getElementById('pred-region').value = 'Chennai';
  document.getElementById('pred-month').value = '11';
  document.getElementById('pred-year').value = '2026';
  document.getElementById('pred-beneficiaries').value = '12500';
  document.getElementById('pred-stock').value = '3800';
  document.getElementById('pred-prev-demand').value = '4200';
  document.getElementById('pred-safety-stock').value = '500';

  isCustomScenario = true;
  updateSourceBadges(true);

  const bBen = document.getElementById('badge-ben');
  if (bBen) { bBen.className = 'badge badge-warning'; bBen.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario (12,500)'; }
  const bStock = document.getElementById('badge-stock');
  if (bStock) { bStock.className = 'badge badge-warning'; bStock.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario (3,800 kg)'; }

  executeDemandForecast();
}
