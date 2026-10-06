/**
 * AI-Powered Smart PDS - Inventory Controller
 */

let inventoryAlertsData = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadInventoryData();

  document.getElementById('adjust-stock-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const com = document.getElementById('adjust-commodity').value;
    const reg = document.getElementById('adjust-region').value;
    const stock = parseFloat(document.getElementById('adjust-new-stock').value);

    try {
      const res = await API.updateInventoryStock(com, reg, stock);
      if (res && res.status === 'success') {
        showToast(`Stock updated: ${com} in ${reg} is now ${stock} kg`, 'success');
        closeModal('adjust-stock-modal');
        document.getElementById('adjust-stock-form').reset();
        await loadInventoryData();
      }
    } catch (err) {
      showToast(err.message || 'Error updating stock', 'error');
    }
  });
});

async function loadInventoryData() {
  try {
    const res = await API.getInventoryAlerts();
    if (res && res.status === 'success') {
      inventoryAlertsData = res.data;
      updateInventoryKPIs(inventoryAlertsData);
      renderInventoryTable(inventoryAlertsData);
    }
  } catch (err) {
    showToast('Failed to load inventory alerts', 'error');
  }
}

function updateInventoryKPIs(data) {
  let totalStock = 0;
  let totalShortage = 0;
  let shortageCount = 0;
  let excessCount = 0;

  data.forEach(item => {
    totalStock += (item.current_stock || 0);
    if (item.shortage > 0) {
      totalShortage += item.shortage;
      shortageCount++;
    }
    if (item.status === 'EXCESS') {
      excessCount++;
    }
  });

  document.getElementById('inv-total-stock').innerHTML = `${Math.round(totalStock).toLocaleString()} <span style="font-size:1rem;">kg</span>`;
  document.getElementById('inv-shortage-count').textContent = shortageCount;
  document.getElementById('inv-total-procurement').innerHTML = `${Math.round(totalShortage).toLocaleString()} <span style="font-size:1rem;">kg</span>`;
  document.getElementById('inv-excess-count').textContent = excessCount;
}

function renderInventoryTable(items) {
  const tbody = document.getElementById('inventory-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">No inventory records found.</td></tr>';
    return;
  }

  tbody.innerHTML = items.map(item => {
    let badgeClass = 'badge-success';
    if (item.status === 'SHORTAGE') {
      badgeClass = 'badge-danger';
    } else if (item.status === 'EXCESS') {
      badgeClass = 'badge-purple';
    }

    const delta = item.current_stock - item.predicted_demand;
    const deltaStr = delta >= 0 ? `+${Math.round(delta)} kg` : `${Math.round(delta)} kg`;
    const deltaColor = delta >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';

    return `
      <tr>
        <td><strong>${item.commodity}</strong></td>
        <td><span class="badge badge-info">${item.region}</span></td>
        <td><strong>${Math.round(item.current_stock).toLocaleString()} kg</strong></td>
        <td>${Math.round(item.predicted_demand).toLocaleString()} kg</td>
        <td style="color:${deltaColor}; font-weight:700;">${deltaStr}</td>
        <td><span class="badge ${badgeClass}">${item.status}</span></td>
        <td><strong style="color: ${item.recommended_procurement > 0 ? 'var(--accent-amber)' : 'var(--accent-emerald)'};">${Math.round(item.recommended_procurement).toLocaleString()} kg</strong></td>
        <td style="max-width: 280px; font-size: 0.82rem; color: var(--text-secondary);">${item.message}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="openQuickAdjust('${item.commodity}', '${item.region}', ${item.current_stock})">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function filterInventory() {
  const reg = document.getElementById('inv-filter-region').value;
  const com = document.getElementById('inv-filter-commodity').value;

  const filtered = inventoryAlertsData.filter(item => {
    const matchReg = !reg || item.region === reg;
    const matchCom = !com || item.commodity === com;
    return matchReg && matchCom;
  });

  renderInventoryTable(filtered);
}

function openQuickAdjust(commodity, region, currentStock) {
  document.getElementById('adjust-commodity').value = commodity;
  document.getElementById('adjust-region').value = region;
  document.getElementById('adjust-new-stock').value = currentStock;
  openModal('adjust-stock-modal');
}
