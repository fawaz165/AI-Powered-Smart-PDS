/**
 * AI-Powered Smart PDS - Dashboard Controller
 */

let inventoryChartInstance = null;
let regionChartInstance = null;

document.addEventListener('DOMContentLoaded', async () => {
  await loadDashboardData();
});

async function loadDashboardData() {
  try {
    // 1. Fetch data concurrently
    const [benRes, invRes, alertsRes, txnsRes, fraudRes] = await Promise.all([
      API.getBeneficiaries({ limit: 1 }),
      API.getInventory(),
      API.getInventoryAlerts(),
      API.getTransactions({ limit: 6 }),
      API.getFraudAlerts()
    ]);

    // Update KPIs
    if (benRes && benRes.status === 'success') {
      document.getElementById('kpi-beneficiaries').textContent = benRes.total.toLocaleString();
    }

    let totalStock = 0;
    const commodityStockMap = { Rice: 0, Wheat: 0, Sugar: 0, Dal: 0 };
    const regionStockMap = {};

    if (invRes && invRes.status === 'success') {
      invRes.data.forEach(item => {
        const qty = parseFloat(item.current_stock) || 0;
        totalStock += qty;
        if (commodityStockMap[item.commodity] !== undefined) {
          commodityStockMap[item.commodity] += qty;
        }
        regionStockMap[item.region] = (regionStockMap[item.region] || 0) + qty;
      });
      document.getElementById('kpi-stock').innerHTML = `${Math.round(totalStock).toLocaleString()} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
    }

    // Process Inventory Alerts & Shortages
    let totalPredictedDemand = 0;
    let totalProcurementNeeded = 0;
    let shortageCount = 0;

    if (alertsRes && alertsRes.status === 'success') {
      alertsRes.data.forEach(a => {
        totalPredictedDemand += (a.predicted_demand || 0);
        if (a.shortage > 0) {
          totalProcurementNeeded += a.shortage;
          shortageCount++;
        }
      });

      document.getElementById('kpi-demand').innerHTML = `${Math.round(totalPredictedDemand).toLocaleString()} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;
      document.getElementById('kpi-procurement').innerHTML = `${Math.round(totalProcurementNeeded).toLocaleString()} <span style="font-size: 1rem; font-weight: 500;">kg</span>`;

      const shortageMeta = document.getElementById('kpi-shortage-meta');
      if (shortageCount > 0) {
        shortageMeta.innerHTML = `<span class="meta-alert"><i class="fa-solid fa-triangle-exclamation"></i> ${shortageCount} Depot Shortages</span>`;
        // Show banner
        const banner = document.getElementById('shortage-banner');
        if (banner) {
          banner.style.display = 'flex';
          document.getElementById('banner-title').textContent = `Procurement Alert: ${Math.round(totalProcurementNeeded).toLocaleString()} kg Additional Stock Required`;
          document.getElementById('banner-desc').textContent = `${shortageCount} commodity/region allocations are below anticipated monthly beneficiary demand.`;
        }
      } else {
        shortageMeta.innerHTML = `<span class="meta-up"><i class="fa-solid fa-check"></i> Stock Optimal</span>`;
      }
    }

    // Fraud alerts
    if (fraudRes && fraudRes.status === 'success') {
      const anomalyCount = fraudRes.count || 0;
      document.getElementById('kpi-anomalies').textContent = anomalyCount;
      const navBadge = document.getElementById('nav-fraud-badge');
      if (navBadge && anomalyCount > 0) {
        navBadge.style.display = 'inline-block';
        navBadge.textContent = anomalyCount;
      }
    }

    // Transactions count and table
    if (txnsRes && txnsRes.status === 'success') {
      document.getElementById('kpi-txns').textContent = txnsRes.total.toLocaleString();
      renderRecentTransactions(txnsRes.data);
    }

    // Render Charts
    renderInventoryChart(commodityStockMap);
    renderRegionChart(regionStockMap);

  } catch (err) {
    console.error('Error loading dashboard data:', err);
    showToast('Failed to load dashboard metrics. Check server logs.', 'error');
  }
}

function renderRecentTransactions(transactions) {
  const tbody = document.getElementById('recent-txns-tbody');
  if (!tbody) return;

  if (!transactions || transactions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No recent distribution transactions recorded.</td></tr>';
    return;
  }

  tbody.innerHTML = transactions.map(t => {
    let badgeClass = 'badge-success';
    if (t.risk_level === 'HIGH' || t.status === 'SUSPICIOUS') {
      badgeClass = 'badge-danger';
    } else if (t.risk_level === 'MEDIUM') {
      badgeClass = 'badge-warning';
    }

    return `
      <tr>
        <td><strong>${t.transaction_id}</strong></td>
        <td>${t.beneficiary_id}</td>
        <td><span class="badge badge-info">${t.commodity}</span></td>
        <td><strong>${t.quantity} kg</strong></td>
        <td>${t.ration_shop_id}</td>
        <td>${t.region || 'Chennai'}</td>
        <td><span class="badge ${badgeClass}">${t.status} (${t.risk_level || 'LOW'})</span></td>
        <td style="max-width: 250px; font-size: 0.8rem; color: var(--text-secondary);">${t.reason || 'Normal distribution'}</td>
      </tr>
    `;
  }).join('');
}

function renderInventoryChart(stockMap) {
  const ctx = document.getElementById('inventoryChart');
  if (!ctx) return;

  if (inventoryChartInstance) {
    inventoryChartInstance.destroy();
  }

  const labels = Object.keys(stockMap);
  const data = Object.values(stockMap);
  const bufferLevels = [2500, 1800, 900, 700]; // Representative buffer threshold

  inventoryChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Current Warehouse Stock (kg)',
          data: data,
          backgroundColor: 'rgba(59, 130, 246, 0.75)',
          borderColor: '#3b82f6',
          borderWidth: 1.5,
          borderRadius: 6
        },
        {
          label: 'Minimum Buffer Level (kg)',
          data: bufferLevels,
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
        }
      },
      scales: {
        x: {
          ticks: { color: '#94a3b8' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        y: {
          ticks: { color: '#94a3b8' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      }
    }
  });
}

function renderRegionChart(regionMap) {
  const ctx = document.getElementById('regionChart');
  if (!ctx) return;

  if (regionChartInstance) {
    regionChartInstance.destroy();
  }

  const labels = Object.keys(regionMap);
  const data = Object.values(regionMap);

  regionChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: [
          '#3b82f6',
          '#06b6d4',
          '#10b981',
          '#f59e0b',
          '#8b5cf6'
        ],
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
        }
      },
      cutout: '65%'
    }
  });
}
