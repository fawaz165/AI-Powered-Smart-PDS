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
  // Sync initial live DB values for default commodity & region (automatically triggers forecast)
  await syncDatabaseValues();
  // Load forecast audit history
  await loadForecastHistory();

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
      const rawCount = benRes.total !== undefined ? benRes.total : (benRes.data ? benRes.data.length : 0);
      liveDbBenCount = rawCount;
      document.getElementById('pred-beneficiaries').value = liveDbBenCount;

      const benBadge = document.getElementById('badge-ben');
      if (benBadge) {
        benBadge.className = 'badge badge-info';
        benBadge.innerHTML = `<i class="fa-solid fa-database"></i> Live DB (${liveDbBenCount.toLocaleString()} cards)`;
      }

      const benLabel = document.getElementById('ben-source-label');
      if (benLabel) {
        benLabel.innerHTML = `<span style="color:var(--accent-cyan);"><i class="fa-solid fa-circle-check"></i> Registered cardholders in database: <strong>${liveDbBenCount.toLocaleString()}</strong> (${escapeHtml(region)})</span>`;
      }
    }

    // 3. Reset previous demand baseline badge
    const prevBadge = document.getElementById('badge-prev-demand');
    if (prevBadge) {
      prevBadge.className = 'badge badge-secondary';
      prevBadge.innerHTML = 'Historical Baseline';
    }

    isCustomScenario = false;
    updateSourceBadges(false);
    showToast(`Synchronized live database values for ${commodity} in ${region}`, 'info');

    // Automatically recalculate forecast so assessment card immediately reflects live values
    await executeDemandForecast();
  } catch (err) {
    console.warn('Could not sync live DB values:', err);
  }
}

function onParameterChange() {
  if (!isCustomScenario) {
    syncDatabaseValues();
  } else {
    executeDemandForecast();
  }
}

function onFieldManualEdit(fieldName) {
  isCustomScenario = true;
  updateSourceBadges(true);

  if (fieldName === 'ben') {
    const b = document.getElementById('badge-ben');
    if (b) { b.className = 'badge badge-warning'; b.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario Value'; }
    const lbl = document.getElementById('ben-source-label');
    if (lbl) lbl.innerHTML = '<span style="color:var(--accent-amber);"><i class="fa-solid fa-pen"></i> Manually customized scenario cardholder count</span>';
  } else if (fieldName === 'stock') {
    const b = document.getElementById('badge-stock');
    if (b) { b.className = 'badge badge-warning'; b.innerHTML = '<i class="fa-solid fa-pen"></i> Scenario Value'; }
    const lbl = document.getElementById('stock-source-label');
    if (lbl) lbl.innerHTML = '<span style="color:var(--accent-amber);"><i class="fa-solid fa-pen"></i> Manually customized warehouse balance</span>';
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
      formBadge.innerHTML = '<i class="fa-solid fa-flask"></i> Simulation Scenario';
    } else {
      const curBen = document.getElementById('pred-beneficiaries')?.value || liveDbBenCount;
      formBadge.className = 'badge badge-info';
      formBadge.innerHTML = `<i class="fa-solid fa-database"></i> Live Database Values (${Number(curBen).toLocaleString()} cards)`;
    }
  }

  if (resBadge) {
    if (isCustom) {
      resBadge.className = 'badge badge-warning';
      resBadge.innerHTML = '<i class="fa-solid fa-flask"></i> Simulation Scenario';
    } else {
      resBadge.className = 'badge badge-info';
      resBadge.innerHTML = '<i class="fa-solid fa-database"></i> Live DB Values';
    }
  }
}

async function loadModelMetrics(dynamic = false) {
  try {
    const res = await API.getModelMetrics(dynamic);
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
              <strong style="color: #fff;">${escapeHtml(name)}</strong>
              ${isBest ? ' <span class="badge badge-success" style="font-size:0.68rem; margin-left:6px;"><i class="fa-solid fa-crown"></i> Winner</span>' : ''}
            </td>
            <td style="font-variant-numeric: tabular-nums;">${Number(m.MAE).toFixed(2)} kg</td>
            <td style="font-variant-numeric: tabular-nums;">${Number(m.MSE).toLocaleString()}</td>
            <td style="font-variant-numeric: tabular-nums;">${Number(m.RMSE).toFixed(2)} kg</td>
            <td><strong style="color:var(--accent-emerald); font-variant-numeric: tabular-nums; font-family:'Outfit',sans-serif;">${Number(m.R2).toFixed(4)}</strong></td>
            <td style="text-align: center;">${isBest ? '<span class="badge badge-info" style="font-size:0.72rem; white-space:nowrap;"><i class="fa-solid fa-check"></i> Active in Production</span>' : '<span class="badge badge-secondary" style="background:rgba(255,255,255,0.05); color:#94a3b8; font-size:0.72rem; white-space:nowrap;">Benchmarked</span>'}</td>
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

      // Confidence Interval Display
      const conf = d.confidence_range;
      const confRangeEl = document.getElementById('res-confidence-range');
      if (confRangeEl) {
        const low = conf?.lower_bound ?? conf?.lower_bound_kg;
        const high = conf?.upper_bound ?? conf?.upper_bound_kg;
        const margin = conf?.margin_of_error_kg;
        if (conf && conf.available !== false && typeof low === 'number' && typeof high === 'number' && !isNaN(low) && !isNaN(high)) {
          confRangeEl.textContent = `${Math.round(low).toLocaleString()} kg – ${Math.round(high).toLocaleString()} kg (±${Math.round(margin || 0).toLocaleString()} kg)`;
        } else {
          confRangeEl.textContent = 'Not Available';
        }
      }

      // Actual vs Predicted Comparison
      const act = d.actual_comparison;
      const actContainer = document.getElementById('res-actual-container');
      const actText = document.getElementById('res-actual-text');
      if (actContainer && actText) {
        const hasActual = act && (act.available === true || act.has_actual_data === true) && act.actual_demand_kg !== null && act.actual_demand_kg !== undefined;
        if (hasActual) {
          actContainer.style.display = 'block';
          const diffVal = act.variance_kg ?? act.difference_kg ?? 0;
          const diffSign = diffVal >= 0 ? '+' : '';
          const varPct = act.variance_pct ?? act.variance_percentage ?? 0;
          const interpretation = act.interpretation || (diffVal >= 0 ? 'Demand higher than historical ledger' : 'Offtake within capacity');
          actText.innerHTML = `Actual Ledger: <strong>${Math.round(act.actual_demand_kg).toLocaleString()} kg</strong> &bull; Variance: <strong>${diffSign}${Math.round(diffVal).toLocaleString()} kg (${diffSign}${varPct}%)</strong> &bull; <em>${escapeHtml(interpretation)}</em>`;
        } else {
          actContainer.style.display = 'none';
        }
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
        factorsGrid.innerHTML = explanation.factors.map(f => {
          let badgeClass = 'badge-secondary';
          if (f.impact && (f.impact.includes('+') || f.impact === 'Primary (+)')) {
            badgeClass = 'badge-info';
          } else if (f.impact === 'Deficit') {
            badgeClass = 'badge-danger';
          } else if (f.impact === 'Adequate' || f.impact === 'Optimal') {
            badgeClass = 'badge-success';
          }
          return `
            <div class="factor-card-item">
              <div class="factor-card-header">
                <span class="factor-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
                <span class="badge ${badgeClass} factor-badge">${escapeHtml(f.impact)}</span>
              </div>
              <div class="factor-value">${escapeHtml(f.value)}</div>
              <div class="factor-detail">${escapeHtml(f.detail)}</div>
            </div>
          `;
        }).join('');
      }

      // 5. Mathematical Calculation Breakdown
      const bd = d.calculation_breakdown || {};
      const breakdownEl = document.getElementById('res-calculation-breakdown');
      if (breakdownEl) {
        const rawPred = Math.round(bd.raw_pipeline_prediction || d.predicted_demand).toLocaleString();
        const finalDemand = Math.round(d.predicted_demand).toLocaleString();
        const baseDemand = Math.round(bd.baseline_demand || prevDemand).toLocaleString();
        const stockVal = Math.round(d.current_stock).toLocaleString();
        const bufferVal = Math.round(d.safety_stock || 0).toLocaleString();
        const grossVal = Math.round(bd.gross_requirement || ((d.predicted_demand || 0) + (d.safety_stock || 0))).toLocaleString();
        const shortageVal = Math.round(d.shortage).toLocaleString();
        const procureVal = Math.round(d.recommended_procurement).toLocaleString();
        const seasonalIdx = (bd.seasonal_multiplier || 1.0).toFixed(2);
        const seasonalLbl = bd.seasonal_label || 'Standard Baseline';
        const trendText = bd.annual_trend_factor > 1.0 ? ` &times; ${bd.annual_trend_factor.toFixed(2)} (${d.year} forward trend)` : '';

        breakdownEl.innerHTML = `
          <div style="margin-bottom:3px;">&bull; <strong>1. Input Scale:</strong> ${d.beneficiary_count.toLocaleString()} cardholder families (${isCustomScenario ? 'Simulated Scale' : 'Live DB'}) &bull; Baseline momentum: ${baseDemand} kg</div>
          <div style="margin-bottom:3px;">&bull; <strong>2. Seasonal Multiplier:</strong> ${seasonalIdx}x (${escapeHtml(seasonalLbl)}) applied to festival/climatic seasonal curve</div>
          <div style="margin-bottom:3px;">&bull; <strong>3. ML Regression Model:</strong> Pipeline preprocessor &rarr; ${escapeHtml(d.model_used || 'Linear Regression')} &rarr; <strong style="color:var(--accent-cyan); font-variant-numeric: tabular-nums;">${rawPred} kg</strong></div>
          <div style="margin-bottom:3px;">&bull; <strong>4. Final Predicted Demand:</strong> Base Prediction (${rawPred} kg)${trendText} &rarr; <strong style="color:#fff; font-size:0.82rem; font-variant-numeric: tabular-nums;">${finalDemand} kg</strong></div>
          <div style="margin-bottom:3px;">&bull; <strong>5. Gross Requirement:</strong> Predicted Demand (${finalDemand} kg) + Safety Buffer (${bufferVal} kg) = <strong style="color:var(--accent-cyan); font-variant-numeric: tabular-nums;">${grossVal} kg</strong></div>
          <div style="margin-bottom:3px;">&bull; <strong>6. Net Shortage:</strong> max(0, Demand [${finalDemand}] &minus; Depot Stock [${stockVal}]) = <strong style="color:var(--accent-rose); font-variant-numeric: tabular-nums;">${shortageVal} kg</strong></div>
          <div>&bull; <strong>7. Procurement Recommended:</strong> max(0, Gross Need [${grossVal}] &minus; Depot Stock [${stockVal}]) = <strong style="color:var(--accent-amber); font-weight:700; font-variant-numeric: tabular-nums;">${procureVal} kg</strong></div>
        `;
      }

      showToast(`Calculated demand: ${Math.round(d.predicted_demand).toLocaleString()} kg for ${commodity} in ${region}`, 'success');
      loadForecastHistory();
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

/**
 * Loads and renders the archival forecast history from backend
 */
async function loadForecastHistory() {
  const tbody = document.getElementById('forecast-history-tbody');
  if (!tbody) return;

  try {
    const res = await API.getForecastHistory({ limit: 10 });
    if (res && res.status === 'success' && Array.isArray(res.data) && res.data.length > 0) {
      tbody.innerHTML = res.data.map(h => {
        const dt = h.created_at_formatted || (h.created_at ? new Date(h.created_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : 'Recent');
        const conf = h.confidence_range;
        const low = conf?.lower_bound ?? conf?.lower_bound_kg;
        const high = conf?.upper_bound ?? conf?.upper_bound_kg;
        const confStr = (conf && conf.available !== false && typeof low === 'number' && typeof high === 'number' && !isNaN(low) && !isNaN(high))
          ? `${Math.round(low).toLocaleString()} – ${Math.round(high).toLocaleString()} kg`
          : 'Not Available';
        const isSim = h.data_source === 'USER_SCENARIO' || h.data_source === 'SIMULATION_SCENARIO' || (h.beneficiary_count && h.beneficiary_count >= 1000);
        return `
          <tr>
            <td style="font-size:0.78rem; color:var(--text-muted); white-space: nowrap;">${escapeHtml(dt)}</td>
            <td><span class="badge badge-info">${escapeHtml(h.commodity)}</span></td>
            <td><strong>${escapeHtml(h.region || h.district || 'Chennai')}</strong></td>
            <td style="font-variant-numeric: tabular-nums;">${escapeHtml(h.month || '')}/${escapeHtml(h.year || '')}</td>
            <td>
              <span class="badge badge-secondary" style="font-size:0.72rem;">${escapeHtml(h.model_used || 'Linear Regression')}</span>
              <span class="badge ${isSim ? 'badge-warning' : 'badge-info'}" style="font-size:0.62rem; margin-left:4px;">${isSim ? 'Simulated' : 'Live DB'}</span>
            </td>
            <td><strong style="color:#fff; font-variant-numeric: tabular-nums;">${Math.round(h.predicted_demand).toLocaleString()} kg</strong></td>
            <td style="font-variant-numeric: tabular-nums; font-size:0.78rem; font-weight: 600; color:var(--accent-cyan); white-space: nowrap;">${confStr}</td>
            <td><strong style="color:var(--accent-amber); font-variant-numeric: tabular-nums;">${Math.round(h.recommended_procurement || 0).toLocaleString()} kg</strong></td>
          </tr>
        `;
      }).join('');
    } else {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 18px;">No forecast history records logged yet. Run a prediction to record an entry.</td></tr>';
    }
  } catch (err) {
    console.warn('Could not load forecast history:', err);
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 18px;">History temporarily unavailable.</td></tr>';
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
  if (bBen) { bBen.className = 'badge badge-warning'; bBen.innerHTML = '<i class="fa-solid fa-flask"></i> Simulated (12,500)'; }
  const lblBen = document.getElementById('ben-source-label');
  if (lblBen) { lblBen.innerHTML = '<span style="color:var(--accent-amber);"><i class="fa-solid fa-flask"></i> Operational depot simulation scale (12,500 cardholders)</span>'; }

  const bStock = document.getElementById('badge-stock');
  if (bStock) { bStock.className = 'badge badge-warning'; bStock.innerHTML = '<i class="fa-solid fa-flask"></i> Simulated (3,800 kg)'; }
  const lblStock = document.getElementById('stock-source-label');
  if (lblStock) { lblStock.innerHTML = '<span style="color:var(--accent-amber);"><i class="fa-solid fa-flask"></i> Simulated depot stock</span>'; }

  const bPrev = document.getElementById('badge-prev-demand');
  if (bPrev) { bPrev.className = 'badge badge-warning'; bPrev.innerHTML = '<i class="fa-solid fa-flask"></i> Simulated (4,200 kg)'; }

  const bBuf = document.getElementById('badge-safety-stock');
  if (bBuf) { bBuf.className = 'badge badge-secondary'; bBuf.innerHTML = 'Buffer (500 kg)'; }

  executeDemandForecast();
}
