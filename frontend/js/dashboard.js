/**
 * AI-Powered Smart PDS - Dashboard Controller
 * Robust, XSS-safe, resilient dashboard supporting dynamic inventory buffers,
 * arbitrary regional distributions, and live ML health telemetry.
 */

let inventoryChartInstance = null;
let regionChartInstance = null;

document.addEventListener('DOMContentLoaded', async () => {
  await loadDashboardData();
});

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
    // 1. Concurrently fetch all operational telemetry via Promise.allSettled()
    const results = await Promise.allSettled([
      API.getBeneficiaries({ limit: 1 }),
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
    if (benRes && benRes.status === 'success') {
      const totalBens = Number(benRes.total || (benRes.data ? benRes.data.length : 0));
      document.getElementById('kpi-beneficiaries').textContent = totalBens.toLocaleString();
    } else {
      document.getElementById('kpi-beneficiaries').textContent = '--';
    }

    // 4. Inventory Warehouse Stock & Buffer Analysis
    let totalStock = 0;
    const commodityStockMap = {};
    const commodityBufferMap = {};
    const regionStockMap = {};

    if (invRes && invRes.status === 'success' && Array.isArray(invRes.data)) {
      invRes.data.forEach(item => {
        const commodity = item.commodity || 'Unknown';
        const region = item.region || 'Unknown';
        const currentStock = parseFloat(item.current_stock) || 0;
        const bufferStock = parseFloat(item.buffer_stock) || 0;

        totalStock += currentStock;
        commodityStockMap[commodity] = (commodityStockMap[commodity] || 0) + currentStock;
        commodityBufferMap[commodity] = (commodityBufferMap[commodity] || 0) + bufferStock;
        regionStockMap[region] = (regionStockMap[region] || 0) + currentStock;
      });

      document.getElementById('kpi-stock').innerHTML = `${Math.round(totalStock).toLocaleString()} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      
      // Update dynamic district counts across UI
      const uniqueDistricts = Object.keys(regionStockMap).length;
      const kpiDistrictsEl = document.getElementById('kpi-districts-count');
      if (kpiDistrictsEl) kpiDistrictsEl.textContent = uniqueDistricts;
      const chartRegionsBadge = document.getElementById('chart-regions-badge');
      if (chartRegionsBadge) chartRegionsBadge.textContent = `${uniqueDistricts} District${uniqueDistricts === 1 ? '' : 's'}`;

      // Render Charts with live database values
      renderInventoryChart(commodityStockMap, commodityBufferMap);
      renderRegionChart(regionStockMap);
    } else {
      document.getElementById('kpi-stock').innerHTML = `-- <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
    }

    // 5. Intelligent Demand & Shortage Calculations
    let totalPredictedDemand = 0;
    let totalProcurementNeeded = 0;
    let shortageCount = 0;

    if (alertsRes && alertsRes.status === 'success' && Array.isArray(alertsRes.data)) {
      alertsRes.data.forEach(alertItem => {
        const pred = parseFloat(alertItem.predicted_demand) || 0;
        const shortage = parseFloat(alertItem.shortage) || 0;

        totalPredictedDemand += pred;
        if (shortage > 0) {
          totalProcurementNeeded += shortage;
          shortageCount++;
        }
      });

      document.getElementById('kpi-demand').innerHTML = `${Math.round(totalPredictedDemand).toLocaleString()} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      document.getElementById('kpi-procurement').innerHTML = `${Math.round(totalProcurementNeeded).toLocaleString()} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;

      const shortageMeta = document.getElementById('kpi-shortage-meta');
      const shortageBanner = document.getElementById('shortage-banner');

      if (shortageCount > 0) {
        if (shortageMeta) {
          shortageMeta.innerHTML = `<span class="meta-alert"><i class="fa-solid fa-triangle-exclamation"></i> ${shortageCount} Depot Shortage${shortageCount === 1 ? '' : 's'}</span>`;
        }
        if (shortageBanner) {
          shortageBanner.style.display = 'flex';
          const bannerTitle = document.getElementById('banner-title');
          const bannerDesc = document.getElementById('banner-desc');
          if (bannerTitle) bannerTitle.textContent = `Procurement Alert: ${Math.round(totalProcurementNeeded).toLocaleString()} kg Additional Stock Required`;
          if (bannerDesc) bannerDesc.textContent = `${shortageCount} regional commodity allocations are currently below anticipated monthly demand.`;
        }
      } else {
        if (shortageMeta) {
          shortageMeta.innerHTML = `<span class="meta-up"><i class="fa-solid fa-check"></i> Stock Optimal</span>`;
        }
        if (shortageBanner) {
          shortageBanner.style.display = 'none';
        }
      }
    } else {
      document.getElementById('kpi-demand').innerHTML = `-- <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      document.getElementById('kpi-procurement').innerHTML = `-- <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
    }

    // 6. Fraud Alerts & Outliers KPI
    if (fraudRes && fraudRes.status === 'success') {
      const pendingCount = fraudRes.pending_count !== undefined 
        ? Number(fraudRes.pending_count) 
        : (fraudRes.count !== undefined 
            ? Number(fraudRes.count) 
            : (Array.isArray(fraudRes.data) ? fraudRes.data.filter(a => a.status === 'PENDING_REVIEW').length : 0));

      const kpiAnomalies = document.getElementById('kpi-anomalies');
      if (kpiAnomalies) kpiAnomalies.textContent = pendingCount;

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
        if (pendingCount > 0) {
          anomalyMeta.innerHTML = `<span class="meta-alert"><i class="fa-solid fa-magnifying-glass-chart"></i></span> Pending Admin Review`;
        } else {
          anomalyMeta.innerHTML = `<span class="meta-up"><i class="fa-solid fa-circle-check"></i></span> All Clear (0 Pending)`;
        }
      }
    } else {
      const kpiAnomalies = document.getElementById('kpi-anomalies');
      if (kpiAnomalies) kpiAnomalies.textContent = '--';
    }

    // 7. Transactions Ledger Count & Safe Table Rendering
    if (txnsRes && txnsRes.status === 'success') {
      const totalTxns = Number(txnsRes.total || (txnsRes.data ? txnsRes.data.length : 0));
      document.getElementById('kpi-txns').textContent = totalTxns.toLocaleString();
      renderRecentTransactions(txnsRes.data || []);
    } else {
      document.getElementById('kpi-txns').textContent = '--';
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
    if (pulseDot) {
      pulseDot.style.background = '#f43f5e';
      pulseDot.style.boxShadow = '0 0 10px rgba(244, 63, 94, 0.6)';
    }
    return;
  }

  const healthData = mlRes.data || {};
  statusText.textContent = healthData.status_text || 'ML Models Active';

  if (pulseDot) {
    if (healthData.health === 'HEALTHY') {
      pulseDot.style.background = '#10b981';
      pulseDot.style.boxShadow = '0 0 10px rgba(16, 185, 129, 0.6)';
    } else if (healthData.health === 'DEGRADED') {
      pulseDot.style.background = '#f59e0b';
      pulseDot.style.boxShadow = '0 0 10px rgba(245, 158, 11, 0.6)';
    } else {
      pulseDot.style.background = '#f43f5e';
      pulseDot.style.boxShadow = '0 0 10px rgba(244, 63, 94, 0.6)';
    }
  }
}

/**
 * Safely renders recent distribution transactions with complete HTML entity escaping.
 */
function renderRecentTransactions(transactions) {
  const tbody = document.getElementById('recent-txns-tbody');
  if (!tbody) return;

  if (!transactions || transactions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No recent distribution transactions recorded.</td></tr>';
    return;
  }

  tbody.innerHTML = transactions.map(t => {
    const rawStatus = (t.status || 'NORMAL').toUpperCase();
    const rawRisk = (t.risk_level || 'LOW').toUpperCase();

    let badgeClass = 'badge-success';
    if (rawRisk === 'HIGH' || rawStatus === 'SUSPICIOUS' || rawStatus === 'HIGH_RISK') {
      badgeClass = 'badge-danger';
    } else if (rawRisk === 'MEDIUM') {
      badgeClass = 'badge-warning';
    }

    const safeTxnId = escapeHtml(t.transaction_id || '--');
    const safeBenId = escapeHtml(t.beneficiary_id || '--');
    const safeCommodity = escapeHtml(t.commodity || '--');
    const safeQty = Number(t.quantity || 0).toLocaleString();
    const safeShop = escapeHtml(t.ration_shop_id || '--');
    const safeRegion = escapeHtml(t.region || 'Chennai');
    const safeStatus = escapeHtml(`${rawStatus} (${rawRisk})`);
    const safeReason = escapeHtml(t.reason || 'Normal distribution quota');

    return `
      <tr>
        <td><strong>${safeTxnId}</strong></td>
        <td>${safeBenId}</td>
        <td><span class="badge badge-info">${safeCommodity}</span></td>
        <td><strong>${safeQty} kg</strong></td>
        <td>${safeShop}</td>
        <td>${safeRegion}</td>
        <td><span class="badge ${badgeClass}">${safeStatus}</span></td>
        <td style="max-width: 250px; font-size: 0.8rem; color: var(--text-secondary);">${safeReason}</td>
      </tr>
    `;
  }).join('');
}

/**
 * Renders inventory bar chart dynamically using database stock and buffer thresholds.
 * Zero hardcoded values.
 */
function renderInventoryChart(stockMap, bufferMap) {
  const ctx = document.getElementById('inventoryChart');
  if (!ctx) return;

  if (inventoryChartInstance) {
    inventoryChartInstance.destroy();
  }

  const labels = Object.keys(stockMap);
  if (labels.length === 0) return;

  const currentStockValues = labels.map(c => Math.round(stockMap[c] || 0));
  const bufferLevelValues = labels.map(c => Math.round((bufferMap && bufferMap[c]) || 0));

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
              return ` ${context.dataset.label}: ${Number(context.raw).toLocaleString()} kg`;
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
 * Renders regional allocation doughnut chart dynamically for ANY number of regions.
 */
function renderRegionChart(regionMap) {
  const ctx = document.getElementById('regionChart');
  if (!ctx) return;

  if (regionChartInstance) {
    regionChartInstance.destroy();
  }

  const labels = Object.keys(regionMap);
  if (labels.length === 0) return;

  const data = labels.map(r => Math.round(regionMap[r] || 0));
  const colors = generateDynamicPalette(labels.length);

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
              const val = Number(context.raw).toLocaleString();
              return ` ${label}: ${val} kg`;
            }
          }
        }
      },
      cutout: '65%'
    }
  });
}
