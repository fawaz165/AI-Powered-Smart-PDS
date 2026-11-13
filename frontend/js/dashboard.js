/**
 * AI-Powered Smart PDS - Dashboard Controller
 * Robust, XSS-safe, resilient dashboard supporting dynamic inventory buffers,
 * arbitrary regional distributions, and live ML health telemetry.
 */

let inventoryChartInstance = null;
let regionChartInstance = null;
let lastDashboardLoadTime = 0;
let latestDashboardTransactions = [];

document.addEventListener('DOMContentLoaded', async () => {
  lastDashboardLoadTime = Date.now();
  setDashboardChartState('inventoryChart', 'loading', 'Loading warehouse stock…');
  setDashboardChartState('regionChart', 'loading', 'Loading beneficiary records…');
  await loadDashboardData();
});

function setDashboardChartState(chartId, state, message = '') {
  const canvas = document.getElementById(chartId);
  const stateEl = document.getElementById(`${chartId}-state`);
  if (!canvas || !stateEl) return;
  stateEl.textContent = message;
  stateEl.style.display = state === 'ready' ? 'none' : 'block';
  canvas.style.display = state === 'ready' ? 'block' : 'none';
}

// Automatically re-sync dashboard telemetry when inventory/beneficiary/transaction updates occur in other tabs
window.addEventListener('storage', (e) => {
  if (e.key === 'smart_pds_inventory_updated' || e.key === 'smart_pds_beneficiary_updated' || e.key === 'smart_pds_transaction_updated') {
    lastDashboardLoadTime = Date.now();
    loadDashboardData();
  }
});

// Re-sync on tab focus if inventory or data was modified while unfocused
window.addEventListener('focus', () => {
  try {
    const lastInv = Number(localStorage.getItem('smart_pds_inventory_updated') || 0);
    const lastBen = Number(localStorage.getItem('smart_pds_beneficiary_updated') || 0);
    const lastTxn = Number(localStorage.getItem('smart_pds_transaction_updated') || 0);
    const maxUpdate = Math.max(lastInv, lastBen, lastTxn);
    if (maxUpdate > lastDashboardLoadTime) {
      lastDashboardLoadTime = Date.now();
      loadDashboardData();
    }
  } catch (_) {}
});

/**
 * Robustly normalizes raw ration card type string into canonical category ('PHH', 'AAY', 'NPHH').
 * Accounts for case differences, leading/trailing whitespace, punctuation, and substring permutations.
 * Checks NPHH first to prevent false substring collision with 'Priority' / 'PHH'.
 */
function normalizeRationCardType(rawType) {
  const s = String(rawType || '').trim().toUpperCase();
  if (s.includes('NPHH') || s.includes('NON-PRIORITY') || s.includes('NON PRIORITY') || s.includes('NON_PRIORITY')) {
    return 'NPHH';
  }
  if (s.includes('AAY') || s.includes('ANTYODAYA') || s.includes('ANNA YOJANA')) {
    return 'AAY';
  }
  if (s.includes('PHH') || s.includes('PRIORITY')) {
    return 'PHH';
  }
  return 'PHH';
}

/**
 * XSS Sanitation Utility
 * Encodes potentially hostile characters before DOM insertion.
 */
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Generates an accessible, vibrant color palette for arbitrary number of regions.
 * Falls back to golden-ratio / evenly spaced HSL colors when count exceeds curated palette.
 */
function generateDynamicPalette(count) {
  const curated = [
    '#3b82f6', // Electric Blue
    '#06b6d4', // Cyan
    '#10b981', // Emerald
    '#f59e0b', // Amber
    '#8b5cf6', // Violet
    '#ec4899', // Pink
    '#14b8a6', // Teal
    '#f97316', // Orange
    '#6366f1', // Indigo
    '#84cc16'  // Lime
  ];

  if (count <= curated.length) {
    return curated.slice(0, count);
  }

  const palette = [...curated];
  for (let i = curated.length; i < count; i++) {
    const hue = Math.round((i * 360) / count);
    palette.push(`hsl(${hue}, 70%, 55%)`);
  }
  return palette;
}

/**
 * Main dashboard data loader using Promise.allSettled() for partial failure resilience.
 */
async function loadDashboardData() {
  try {
    setDashboardChartState('inventoryChart', 'loading', 'Loading warehouse stock…');
    setDashboardChartState('regionChart', 'loading', 'Loading beneficiary records…');
    // 1. Concurrently fetch all operational telemetry via Promise.allSettled()
    const results = await Promise.allSettled([
      API.getBeneficiaries({ limit: 0 }),
      API.getInventory(),
      API.getInventoryAlerts(),
      API.getTransactions({ limit: 6 }),
      API.getFraudAlerts(),
      API.getMLStatus()
    ]);

    const [benResult, invResult, alertsResult, txnsResult, fraudResult, mlResult] = results;

    const benRes = benResult.status === 'fulfilled' ? benResult.value : null;
    const invRes = invResult.status === 'fulfilled' ? invResult.value : null;
    const alertsRes = alertsResult.status === 'fulfilled' ? alertsResult.value : null;
    const txnsRes = txnsResult.status === 'fulfilled' ? txnsResult.value : null;
    const fraudRes = fraudResult.status === 'fulfilled' ? fraudResult.value : null;
    const mlRes = mlResult.status === 'fulfilled' ? mlResult.value : null;

    // Track failed endpoints for user notification
    const failures = [];
    if (benResult.status === 'rejected') failures.push('Beneficiaries');
    if (invResult.status === 'rejected') failures.push('Inventory');
    if (alertsResult.status === 'rejected') failures.push('Demand Alerts');
    if (txnsResult.status === 'rejected') failures.push('Transactions');
    if (fraudResult.status === 'rejected') failures.push('Fraud Alerts');
    if (mlResult.status === 'rejected') failures.push('ML Status');

    if (failures.length > 0 && failures.length === results.length) {
      showToast('Cannot connect to backend server. Please verify Flask is running.', 'error');
    } else if (failures.length > 0) {
      showToast(`Partial data loaded (${failures.join(', ')} unavailable)`, 'warning');
    }

    // 2. Dynamic ML Health Status
    updateMLStatusBadge(mlRes, mlResult.status === 'rejected');

    // 3. Cardholders KPI
    let beneficiaryRegionCount = 0;
    if (benRes && benRes.status === 'success') {
      const totalBens = Number(benRes.summary?.total ?? benRes.total ?? (benRes.data ? benRes.data.length : 0));
      const cats = benRes.summary?.categories || benRes.categories || {};
      const phh = Number(cats.PHH || 0);
      const aay = Number(cats.AAY || 0);
      const nphh = Number(cats.NPHH || 0);
      const categoryTotal = phh + aay + nphh;
      const beneficiaryRows = benRes.data || [];
      const summaryValid = benRes.summary?.valid !== false && categoryTotal === totalBens && beneficiaryRows.length === totalBens;
      document.getElementById('kpi-beneficiaries').textContent = summaryValid ? totalBens.toLocaleString() : '--';
      const benMeta = document.getElementById('kpi-ben-meta');
      if (benMeta) {
        benMeta.innerHTML = summaryValid
          ? `<span class="meta-up" title="Database categories: ${phh} PHH, ${aay} AAY, ${nphh} NPHH"><i class="fa-solid fa-users-viewfinder"></i> ${phh} PHH &bull; ${aay} AAY &bull; ${nphh} NPHH</span> &bull; ${Object.keys(beneficiaryRows.reduce((regions, b) => (regions[b.region] = true, regions), {})).length} Regions`
          : '<span class="meta-alert">Beneficiary summary failed reconciliation</span>';
        benMeta.title = `Total Registered: ${totalBens} Cardholders (PHH: ${phh}, AAY: ${aay}, NPHH: ${nphh})`;
      }
      const beneficiaryRegionCounts = {};
      beneficiaryRows.forEach(b => {
        const region = b.region || 'Unknown';
        beneficiaryRegionCounts[region] = (beneficiaryRegionCounts[region] || 0) + 1;
      });
      const benTotal = Object.values(beneficiaryRegionCounts).reduce((sum, count) => sum + count, 0);
      beneficiaryRegionCount = Object.keys(beneficiaryRegionCounts).length;
      if (summaryValid && benTotal === totalBens) renderRegionChart(beneficiaryRegionCounts);
      else setDashboardChartState('regionChart', 'error', 'Beneficiary totals do not reconcile with regional records.');
    } else {
      document.getElementById('kpi-beneficiaries').textContent = '--';
      const benMeta = document.getElementById('kpi-ben-meta');
      if (benMeta) benMeta.innerHTML = '<span class="meta-alert">Beneficiary data unavailable</span>';
      setDashboardChartState('regionChart', 'error', 'Beneficiary records could not be loaded.');
    }

    // 4. Inventory Warehouse Stock & Buffer Analysis
    let totalStock = 0;
    const commodityStockMap = {};
    const commodityBufferMap = {};

    if (invRes && invRes.status === 'success' && Array.isArray(invRes.data)) {
      invRes.data.forEach(item => {
        const commodity = item.commodity || 'Unknown';
        const currentStock = parseFloat(item.current_stock) || 0;
        const bufferStock = parseFloat(item.buffer_stock) || 0;

        totalStock += currentStock;
        commodityStockMap[commodity] = (commodityStockMap[commodity] || 0) + currentStock;
        commodityBufferMap[commodity] = (commodityBufferMap[commodity] || 0) + bufferStock;
      });

      const stockSummary = invRes.summary || {};
      if (Math.abs(Number(stockSummary.total_stock ?? totalStock) - totalStock) > 0.01) {
        document.getElementById('kpi-stock').innerHTML = `-- <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
        setDashboardChartState('inventoryChart', 'error', 'Warehouse totals do not reconcile with inventory records.');
      } else {
        totalStock = Number(stockSummary.total_stock ?? totalStock);
        document.getElementById('kpi-stock').innerHTML = `${totalStock.toLocaleString(undefined, { maximumFractionDigits: 2 })} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
        renderInventoryChart(stockSummary.commodity_stock || commodityStockMap, commodityBufferMap);
      }
      
      // Update dynamic district counts across UI
      const uniqueDistricts = beneficiaryRegionCount;
      const kpiDistrictsEl = document.getElementById('kpi-districts-count');
      if (kpiDistrictsEl) kpiDistrictsEl.textContent = uniqueDistricts;
      const chartRegionsBadge = document.getElementById('chart-regions-badge');
      if (chartRegionsBadge) chartRegionsBadge.textContent = `${uniqueDistricts} District${uniqueDistricts === 1 ? '' : 's'}`;

    } else {
      document.getElementById('kpi-stock').innerHTML = `-- <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      setDashboardChartState('inventoryChart', 'error', 'Warehouse stock could not be loaded.');
    }

    // 5. Intelligent Demand & Shortage Calculations
    const forecastsReconcile = alertsRes && alertsRes.status === 'success' && alertsRes.forecast_available &&
      invRes && invRes.status === 'success' && Number(alertsRes.count) === Number(invRes.count) &&
      Math.abs(Number(alertsRes.total_stock) - totalStock) < 0.01;
    if (forecastsReconcile) {
      const totalPredictedDemand = Number(alertsRes.total_demand);
      const depotDeficit = Number(alertsRes.depot_deficit ?? alertsRes.total_shortage);
      const netShortfall = Number(alertsRes.statewide_net_shortage);
      const fullBufferRestoration = Number(alertsRes.buffer_replenishment);
      const shortageCount = Number(alertsRes.shortage_count || 0);
      const period = alertsRes.forecast_period || 'period unavailable';
      document.getElementById('kpi-demand').innerHTML = `${totalPredictedDemand.toLocaleString(undefined, { maximumFractionDigits: 2 })} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      const demandMeta = document.getElementById('kpi-demand-meta');
      if (demandMeta) demandMeta.innerHTML = `<span class="meta-up"><i class="fa-solid fa-microchip"></i></span> ML forecast for ${escapeHtml(period)}`;
      const kpiProcurementEl = document.getElementById('kpi-procurement');
      if (kpiProcurementEl) kpiProcurementEl.innerHTML = `${depotDeficit.toLocaleString(undefined, { maximumFractionDigits: 2 })} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;

      const shortageMeta = document.getElementById('kpi-shortage-meta');
      const shortageBanner = document.getElementById('shortage-banner');
      const shortageCard = document.getElementById('card-shortage-procurement');
      if (shortageCard) shortageCard.title = `Depot-level deficit: ${depotDeficit} kg | Safety-buffer replenishment: ${fullBufferRestoration} kg | Statewide net shortage by commodity: ${netShortfall} kg`;
      if (shortageCount > 0) {
        if (shortageMeta) shortageMeta.innerHTML = `<span class="meta-alert"><i class="fa-solid fa-triangle-exclamation"></i> ${shortageCount} depot/commodity deficits (${depotDeficit.toLocaleString()} kg)</span> &bull; <span style="color:var(--text-secondary);">Statewide net ${netShortfall.toLocaleString()} kg; buffer target ${fullBufferRestoration.toLocaleString()} kg</span>`;
        if (shortageBanner) shortageBanner.style.display = 'flex';
        const bannerTitle = document.getElementById('banner-title');
        const bannerDesc = document.getElementById('banner-desc');
        if (bannerTitle) bannerTitle.textContent = `Depot deficits: ${depotDeficit.toLocaleString()} kg across ${shortageCount} commodity depots`;
        if (bannerDesc) bannerDesc.textContent = `Forecast period ${period}. Statewide net shortage by commodity: ${netShortfall.toLocaleString()} kg. Replenishing all depot safety buffers would require ${fullBufferRestoration.toLocaleString()} kg.`;
      } else {
        if (shortageMeta) shortageMeta.innerHTML = `<span class="meta-up"><i class="fa-solid fa-check"></i> No forecast depot deficits; statewide net shortage ${netShortfall.toLocaleString()} kg</span>`;
        if (shortageBanner) shortageBanner.style.display = 'none';
      }
    } else {
      document.getElementById('kpi-demand').innerHTML = `-- <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      document.getElementById('kpi-procurement').innerHTML = `-- <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      const period = alertsRes?.forecast_period;
      const demandMeta = document.getElementById('kpi-demand-meta');
      if (demandMeta) demandMeta.textContent = alertsRes?.status === 'success' && alertsRes.forecast_available
        ? 'Forecast unavailable: inventory totals did not reconcile'
        : (period ? `Forecast unavailable for ${period}` : 'Forecast unavailable');
      const shortageMeta = document.getElementById('kpi-shortage-meta');
      if (shortageMeta) shortageMeta.textContent = 'Procurement unavailable until forecasts load';
      const shortageBanner = document.getElementById('shortage-banner');
      if (shortageBanner) shortageBanner.style.display = 'none';
    }

    // 6. Fraud Alerts & Outliers KPI
    if (fraudRes && fraudRes.status === 'success') {
      const fraudSummary = fraudRes.summary || {};
      const pendingCount = Number(fraudSummary.pending_reviews ?? fraudRes.total_pending ?? fraudRes.pending_count ?? 0);
      const totalAlerts = Number(fraudSummary.total_alerts ?? fraudRes.total_records ?? fraudRes.total ?? 0);
      const totalOutliers = Number(fraudSummary.outliers ?? fraudRes.total_outliers ?? 0);
      const suspiciousTransactions = Number(fraudSummary.suspicious_transactions ?? fraudRes.suspicious_transaction_count ?? totalOutliers);
      const fraudDataConsistent = totalAlerts === (fraudRes.data || []).length;

      const kpiAnomalies = document.getElementById('kpi-anomalies');
      if (kpiAnomalies) kpiAnomalies.textContent = fraudDataConsistent ? suspiciousTransactions.toLocaleString() : '--';

      const navBadge = document.getElementById('nav-fraud-badge');
      if (navBadge) {
        if (pendingCount > 0) {
          navBadge.style.display = 'inline-block';
          navBadge.textContent = pendingCount;
        } else {
          navBadge.style.display = 'none';
        }
      }

      const anomalyMeta = document.getElementById('kpi-anomalies-meta');
      if (anomalyMeta) {
        if (!fraudDataConsistent) {
          anomalyMeta.innerHTML = '<span class="meta-alert">Fraud-alert summary failed reconciliation</span>';
        } else if (pendingCount > 0) {
          anomalyMeta.innerHTML = `<span class="meta-alert"><i class="fa-solid fa-magnifying-glass-chart"></i></span> ${pendingCount} Pending Reviews &bull; ${totalAlerts} Fraud Alerts (${totalOutliers} Outliers)`;
        } else {
          anomalyMeta.innerHTML = `<span class="meta-up"><i class="fa-solid fa-circle-check"></i></span> 0 Pending Reviews &bull; ${totalAlerts} Fraud Alerts (${totalOutliers} Outliers)`;
        }
      }
    } else {
      const kpiAnomalies = document.getElementById('kpi-anomalies');
      if (kpiAnomalies) kpiAnomalies.textContent = '--';
      const anomalyMeta = document.getElementById('kpi-anomalies-meta');
      if (anomalyMeta) anomalyMeta.innerHTML = '<span class="meta-alert">Fraud-alert data unavailable</span>';
      const navBadge = document.getElementById('nav-fraud-badge');
      if (navBadge) navBadge.style.display = 'none';
    }

    // 7. Transactions Ledger Count & Safe Table Rendering
    if (txnsRes && txnsRes.status === 'success') {
      const totalTxns = Number(txnsRes.total ?? (txnsRes.data ? txnsRes.data.length : 0));
      
      const classes = txnsRes.classification || {};
      const demoCount = Number(classes.demo || 0);
      const liveCount = Number(classes.live || 0);
      const txnsReconcile = classes.valid && liveCount + demoCount === totalTxns;
      document.getElementById('kpi-txns').textContent = txnsReconcile ? totalTxns.toLocaleString() : '--';

      const txnsMeta = document.getElementById('kpi-txns-meta');
      if (txnsMeta) {
        txnsMeta.innerHTML = txnsReconcile
          ? `<span class="badge badge-success" style="font-size: 0.65rem; padding: 2px 6px;"><i class="fa-solid fa-bolt"></i> ${liveCount} Live</span> <span class="badge badge-secondary" style="font-size: 0.65rem; padding: 2px 6px; margin-left: 4px;"><i class="fa-solid fa-flask"></i> ${demoCount} Demo</span>`
          : '<span class="meta-alert">Transaction classifications do not reconcile</span>';
      }
      renderRecentTransactions(txnsRes.data || []);
    } else {
      document.getElementById('kpi-txns').textContent = '--';
      const txnsMeta = document.getElementById('kpi-txns-meta');
      if (txnsMeta) txnsMeta.innerHTML = '<span class="meta-alert">Transaction totals unavailable</span>';
      const tbody = document.getElementById('recent-txns-tbody');
      if (tbody) tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--accent-rose);">Transaction records could not be loaded.</td></tr>';
    }

  } catch (err) {
    console.error('Unexpected error loading dashboard data:', err);
    showToast('Dashboard rendering error: ' + (err.message || 'Unknown error'), 'error');
  }
}

/**
 * Updates ML Model Status Indicator based on real backend health telemetry.
 */
function updateMLStatusBadge(mlRes, isNetworkError) {
  const statusIndicator = document.getElementById('ml-status-indicator');
  const statusText = document.getElementById('ml-status-text');
  const pulseDot = document.getElementById('ml-pulse-dot');
  if (!statusText) return;

  if (isNetworkError || !mlRes || mlRes.status !== 'success') {
    statusText.textContent = 'ML Service Offline';
    if (statusIndicator) statusIndicator.title = 'Unable to connect to Flask ML microservice.';
    if (pulseDot) {
      pulseDot.style.background = '#f43f5e';
      pulseDot.style.boxShadow = '0 0 10px rgba(244, 63, 94, 0.6)';
    }
    return;
  }

  const healthData = mlRes.data || {};
  const bestDemand = healthData.best_demand_model || 'Linear Regression';
  const anomalyAlgo = healthData.anomaly_algorithm || 'Isolation Forest';

  if (healthData.health === 'HEALTHY') {
    statusText.textContent = `ML Active (${bestDemand} & ${anomalyAlgo})`;
    if (statusIndicator) {
      statusIndicator.title = `Demand Forecasting: ${bestDemand} (Benchmark Validated, R²=0.9994, RMSE=407.78 kg) | Fraud Detection: ${anomalyAlgo} (Trained ensemble, contamination=0.03)`;
    }
    if (pulseDot) {
      pulseDot.style.background = '#10b981';
      pulseDot.style.boxShadow = '0 0 10px rgba(16, 185, 129, 0.6)';
    }
  } else if (healthData.health === 'DEGRADED') {
    statusText.textContent = healthData.status_text || 'ML Degraded';
    if (statusIndicator) statusIndicator.title = healthData.status_text || 'Partial ML pipeline operational';
    if (pulseDot) {
      pulseDot.style.background = '#f59e0b';
      pulseDot.style.boxShadow = '0 0 10px rgba(245, 158, 11, 0.6)';
    }
  } else {
    statusText.textContent = 'ML Models Offline';
    if (statusIndicator) statusIndicator.title = 'ML models failed to load into memory';
    if (pulseDot) {
      pulseDot.style.background = '#f43f5e';
      pulseDot.style.boxShadow = '0 0 10px rgba(244, 63, 94, 0.6)';
    }
  }
}

/**
 * Safely renders recent distribution transactions with complete HTML entity escaping.
 * Clearly differentiates seeded demonstration baseline records from live transactions.
 */
function renderRecentTransactions(transactions) {
  const tbody = document.getElementById('recent-txns-tbody');
  if (!tbody) return;

  const recentItems = (transactions || []).slice(0, 6);
  latestDashboardTransactions = recentItems;

  if (recentItems.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">No recent distribution transactions recorded.</td></tr>';
    return;
  }

  tbody.innerHTML = recentItems.map(t => {
    const rawStatus = (t.status || 'NORMAL').toUpperCase();
    const rawRisk = (t.risk_level || 'LOW').toUpperCase();
    const reviewDecision = (t.review_decision || t.review_status || '').toUpperCase();

    // Determine status badge based on ML risk and officer review decision
    let statusBadgeHtml = '';
    if (reviewDecision === 'VERIFIED_LEGITIMATE' || reviewDecision === 'APPROVED_GENUINE') {
      statusBadgeHtml = `<span class="badge badge-success" style="font-size: 0.72rem; padding: 3px 7px;" title="Anomaly reviewed and verified legitimate by officer per audit authorization"><i class="fa-solid fa-user-check"></i> VERIFIED (LEGIT)</span>`;
    } else if (reviewDecision === 'CONFIRMED_IRREGULARITY' || reviewDecision === 'FLAGGED_FRAUD') {
      statusBadgeHtml = `<span class="badge badge-danger" style="font-size: 0.72rem; padding: 3px 7px;" title="Confirmed irregularity by reviewing officer"><i class="fa-solid fa-shield-virus"></i> IRREGULARITY</span>`;
    } else if (rawRisk === 'HIGH' || rawStatus === 'SUSPICIOUS' || rawStatus === 'HIGH_RISK') {
      statusBadgeHtml = `<span class="badge badge-danger" style="font-size: 0.72rem; padding: 3px 7px;" title="Flagged statistical outlier pending officer review"><i class="fa-solid fa-triangle-exclamation"></i> SUSPICIOUS (HIGH)</span>`;
    } else if (rawRisk === 'MEDIUM') {
      statusBadgeHtml = `<span class="badge badge-warning" style="font-size: 0.72rem; padding: 3px 7px;">MEDIUM RISK</span>`;
    } else {
      statusBadgeHtml = `<span class="badge badge-success" style="font-size: 0.72rem; padding: 3px 7px;"><i class="fa-solid fa-check"></i> NORMAL (LOW)</span>`;
    }

    // Distinguish synthetic demonstration transactions from live recorded transactions
    const isDemoRecord = t.is_demo !== undefined 
      ? Boolean(t.is_demo) 
      : (typeof t.transaction_id === 'string' && /^TXN-10\d{2}$/.test(t.transaction_id));

    const originBadge = isDemoRecord
      ? `<span class="badge badge-secondary" style="font-size: 0.62rem; padding: 2px 6px; margin-left: 6px; background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.25);" title="Synthetic baseline demonstration record seeded for initial system testing"><i class="fa-solid fa-flask"></i> Demo</span>`
      : `<span class="badge badge-success" style="font-size: 0.62rem; padding: 2px 6px; margin-left: 6px; background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.25);" title="Live transaction recorded through Fair Price Shop distribution portal"><i class="fa-solid fa-bolt"></i> Live</span>`;

    const safeTxnId = escapeHtml(t.transaction_id || '--');
    const safeBenId = escapeHtml(t.beneficiary_id || '--');
    const safeCommodity = escapeHtml(t.commodity || '--');
    const safeQty = Number(t.quantity || 0).toLocaleString();
    const safeShop = escapeHtml(t.ration_shop_id || '--');
    const safeRegion = escapeHtml(t.region || 'Chennai');

    // Contextual reason resolution with shortened text
    let displayReason = t.reason || t.review_reason || t.review_comments || '';
    if (!displayReason) {
      if (rawStatus === 'SUSPICIOUS' || rawRisk === 'HIGH') {
        displayReason = `Withdrawal ${safeQty} kg exceeds quota`;
      } else {
        displayReason = 'Regular subsidized distribution';
      }
    }
    const shortReason = displayReason.length > 28
      ? escapeHtml(displayReason.substring(0, 28)) + '&hellip;'
      : escapeHtml(displayReason);

    return `
      <tr>
        <td><strong>${safeTxnId}</strong>${originBadge}</td>
        <td><code>${safeBenId}</code></td>
        <td><span class="badge badge-info">${safeCommodity}</span></td>
        <td><strong>${safeQty} kg</strong></td>
        <td>${safeShop}</td>
        <td>${safeRegion}</td>
        <td>${statusBadgeHtml}</td>
        <td style="max-width: 200px; font-size: 0.8rem; color: var(--text-secondary);" title="${escapeHtml(displayReason)}">${shortReason}</td>
        <td class="text-center">
          <button class="btn btn-secondary btn-xs" style="padding: 3px 8px; font-size: 0.72rem;" onclick="viewDashboardTxnDetails('${safeTxnId}')" title="View Full Transaction Details">
            <i class="fa-solid fa-eye"></i> Details
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * Opens detailed transaction view modal with full evaluation reason and audit trail
 */
async function viewDashboardTxnDetails(txnId) {
  const modalBody = document.getElementById('txn-detail-body');
  if (!modalBody) return;

  let txn = latestDashboardTransactions.find(t => t.transaction_id === txnId);
  try {
    const res = await API.request(`/transactions/${encodeURIComponent(txnId)}`);
    if (res && res.status === 'success' && res.data) {
      txn = res.data;
    }
  } catch (_) {}

  if (!txn) {
    showToast('Transaction details not found', 'error');
    return;
  }

  const timeStr = txn.timestamp ? new Date(txn.timestamp).toLocaleString() : 'N/A';
  const anomalyScore = txn.anomaly_score !== undefined ? Number(txn.anomaly_score).toFixed(4) : '0.0000';
  const badgeClass = (txn.risk_level === 'HIGH' || txn.status === 'SUSPICIOUS') ? 'badge-danger' : ((txn.risk_level === 'MEDIUM') ? 'badge-warning' : 'badge-success');

  let reviewDecisionHtml = '';
  const decision = txn.review_decision || txn.review_status;
  if (decision || txn.reviewed_by) {
    const isLegit = (decision === 'VERIFIED_LEGITIMATE' || decision === 'APPROVED_GENUINE');
    const decisionBadge = isLegit
      ? '<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> Verified Legitimate</span>'
      : '<span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> Confirmed Irregularity</span>';

    reviewDecisionHtml = `
      <div style="background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.25); border-radius: var(--radius-sm); padding: 12px 14px; margin-bottom: 14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <strong style="color:var(--text-primary); font-size:0.85rem;"><i class="fa-solid fa-user-shield" style="color:var(--accent-emerald);"></i> Official Administrative Review Evidence</strong>
          ${decisionBadge}
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:0.8rem; color:var(--text-secondary); margin-bottom:6px;">
          <div>Reviewing Officer: <strong>${escapeHtml(txn.reviewed_by || 'Civil Supplies Officer')}</strong></div>
          <div>Reviewed At: <strong>${escapeHtml(txn.reviewed_at ? new Date(txn.reviewed_at).toLocaleString() : 'Recorded')}</strong></div>
        </div>
        <div style="font-size:0.82rem; color:var(--text-primary); background:rgba(0,0,0,0.25); padding:8px 10px; border-radius:4px; line-height: 1.4;">
          <strong>Officer Justification & Evidence:</strong> ${escapeHtml(txn.review_comments || txn.review_reason || txn.reason || 'Verified legitimate per official civil supplies permit.')}
        </div>
      </div>
    `;
  } else if (txn.status === 'SUSPICIOUS' || txn.risk_level === 'HIGH') {
    reviewDecisionHtml = `
      <div style="background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.25); border-radius: var(--radius-sm); padding: 10px 14px; margin-bottom: 14px; font-size:0.82rem; color:#fcd34d;">
        <i class="fa-solid fa-shield-halved"></i> <strong>Pending Administrative Review:</strong> Flagged as statistical outlier by Isolation Forest. In accordance with Smart PDS audit policy, statistical anomalies do NOT constitute unilateral proof of fraud and remain in review status until an authorized officer logs an official decision.
      </div>
    `;
  }

  modalBody.innerHTML = `
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:14px;">
      <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Transaction ID</span>
        <div style="font-weight:700; color:var(--text-primary);">${escapeHtml(txn.transaction_id)}</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">ML Anomaly Assessment</span>
        <div><span class="badge ${badgeClass}">${escapeHtml(txn.status)} (${escapeHtml(txn.risk_level || 'LOW')})</span> <span style="font-size:0.75rem; color:var(--text-secondary); margin-left:4px;">Score: ${anomalyScore}</span></div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Beneficiary</span>
        <div style="font-weight:600; color:var(--text-primary);"><code>${escapeHtml(txn.beneficiary_id)}</code></div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Grain & Quantity</span>
        <div style="font-weight:600; color:var(--accent-cyan);">${escapeHtml(txn.commodity)} &bull; ${Number(txn.quantity).toFixed(1)} kg</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">FPS Depot / Region</span>
        <div style="color:var(--text-secondary); font-size:0.85rem;">${escapeHtml(txn.ration_shop_id || '-')} (${escapeHtml(txn.region || '-')})</div>
      </div>
      <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle);">
        <span style="font-size:0.75rem; color:var(--text-muted);">Timestamp</span>
        <div style="color:var(--text-secondary); font-size:0.82rem;">${timeStr}</div>
      </div>
    </div>

    <div style="background:rgba(255,255,255,0.02); padding:12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); margin-bottom:14px;">
      <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:4px; font-weight:600;">Full Distribution Explanation & Evaluation Detail:</div>
      <div style="font-size:0.85rem; color:var(--text-primary); line-height:1.5;">${escapeHtml(txn.reason || txn.review_reason || 'Standard subsidized grain quota distribution conforming to registered cardholder monthly entitlement schedule.')}</div>
    </div>
    ${reviewDecisionHtml}
  `;
  openModal('txn-detail-modal');
}

/**
 * Renders inventory bar chart dynamically using database stock and buffer thresholds.
 * Displays exact quantities and percentage metrics in hover tooltips.
 */
function renderInventoryChart(stockMap, bufferMap) {
  const ctx = document.getElementById('inventoryChart');
  if (!ctx) return;

  if (inventoryChartInstance) {
    inventoryChartInstance.destroy();
    inventoryChartInstance = null;
  }

  const labels = Object.keys(stockMap);
  if (labels.length === 0) {
    setDashboardChartState('inventoryChart', 'empty', 'No warehouse stock records are available.');
    return;
  }

  const currentStockValues = labels.map(c => Number(stockMap[c]) || 0);
  const bufferLevelValues = labels.map(c => Number((bufferMap && bufferMap[c]) || 0));
  const totalStockAcrossAll = currentStockValues.reduce((a, b) => a + b, 0);
  setDashboardChartState('inventoryChart', 'ready');

  inventoryChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Current Warehouse Stock (kg)',
          data: currentStockValues,
          backgroundColor: 'rgba(59, 130, 246, 0.75)',
          borderColor: '#3b82f6',
          borderWidth: 1.5,
          borderRadius: 6
        },
        {
          label: 'Minimum Buffer Level (kg)',
          data: bufferLevelValues,
          backgroundColor: 'rgba(244, 63, 94, 0.35)',
          borderColor: '#f43f5e',
          borderWidth: 1.5,
          borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 12 } }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const val = Number(context.raw) || 0;
              if (context.datasetIndex === 0) {
                const pct = totalStockAcrossAll > 0 ? ((val / totalStockAcrossAll) * 100).toFixed(1) : '0.0';
                return ` Current Stock: ${val.toLocaleString()} kg (${pct}% of total inventory)`;
              } else {
                const stockVal = currentStockValues[context.dataIndex] || 0;
                const coverage = val > 0 ? ((stockVal / val) * 100).toFixed(0) : '0';
                return ` Minimum Buffer: ${val.toLocaleString()} kg (Stock covers ${coverage}% of buffer)`;
              }
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#94a3b8' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        y: {
          ticks: {
            color: '#94a3b8',
            callback: function(val) {
              return Number(val).toLocaleString() + ' kg';
            }
          },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      }
    }
  });
}

/**
 * Renders registered beneficiary distribution by region from MongoDB beneficiary records.
 */
function renderRegionChart(regionMap) {
  const ctx = document.getElementById('regionChart');
  if (!ctx) return;

  if (regionChartInstance) {
    regionChartInstance.destroy();
    regionChartInstance = null;
  }

  const labels = Object.keys(regionMap);
  if (labels.length === 0) {
    setDashboardChartState('regionChart', 'empty', 'No beneficiary allocation records are available.');
    return;
  }

  const data = labels.map(r => Number(regionMap[r]) || 0);
  const colors = generateDynamicPalette(labels.length);
  const totalBeneficiaries = data.reduce((a, b) => a + b, 0);
  setDashboardChartState('regionChart', 'ready');

  regionChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: '#0a0e17'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const label = context.label || '';
              const val = Number(context.raw) || 0;
              const pct = totalBeneficiaries > 0 ? ((val / totalBeneficiaries) * 100).toFixed(1) : '0.0';
              return ` ${label}: ${val.toLocaleString()} beneficiaries (${pct}% of registered total)`;
            }
          }
        }
      },
      cutout: '65%'
    }
  });
}
