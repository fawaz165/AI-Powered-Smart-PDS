/**
 * AI-Powered Smart PDS - Beneficiaries Controller
 */

let allBeneficiaries = [];

document.addEventListener('DOMContentLoaded', async () => {
  await fetchBeneficiaries();

  document.getElementById('add-beneficiary-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const bid = document.getElementById('new-ben-id').value.trim();
    const name = document.getElementById('new-ben-name').value.trim();
    const region = document.getElementById('new-ben-region').value;
    const size = parseInt(document.getElementById('new-ben-size').value, 10);
    const type = document.getElementById('new-ben-type').value;

    try {
      const res = await API.createBeneficiary({
        beneficiary_id: bid,
        name: name,
        region: region,
        family_size: size,
        ration_card_type: type
      });
      if (res && res.status === 'success') {
        showToast(`Beneficiary ${bid} created successfully!`, 'success');
        closeModal('add-beneficiary-modal');
        document.getElementById('add-beneficiary-form').reset();
        await fetchBeneficiaries();
      }
    } catch (err) {
      showToast(err.message || 'Error creating beneficiary', 'error');
    }
  });
});

async function fetchBeneficiaries() {
  try {
    const res = await API.getBeneficiaries({ limit: 200 });
    if (res && res.status === 'success') {
      allBeneficiaries = res.data;
      renderBeneficiariesTable(allBeneficiaries);
    }
  } catch (err) {
    showToast('Failed to load beneficiaries', 'error');
  }
}

function renderBeneficiariesTable(beneficiaries) {
  const tbody = document.getElementById('beneficiaries-tbody');
  if (!tbody) return;

  if (!beneficiaries || beneficiaries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No cardholders found matching search criteria.</td></tr>';
    return;
  }

  tbody.innerHTML = beneficiaries.map(b => {
    const quotaStr = b.monthly_quota ? `Rice: ${b.monthly_quota.Rice || 0}kg | Wheat: ${b.monthly_quota.Wheat || 0}kg` : 'Standard';
    return `
      <tr>
        <td><strong>${b.beneficiary_id}</strong></td>
        <td>${b.name}</td>
        <td><span class="badge badge-info">${b.region}</span></td>
        <td>${b.family_size} Members</td>
        <td><span class="badge ${b.ration_card_type.includes('AAY') ? 'badge-purple' : 'badge-warning'}">${b.ration_card_type}</span></td>
        <td style="font-size:0.8rem; color:var(--text-secondary);">${quotaStr}</td>
        <td><span class="badge badge-success">Active</span></td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="deleteBeneficiaryItem('${b.beneficiary_id}')" style="color:var(--accent-rose);">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function filterBeneficiaries() {
  const search = document.getElementById('ben-search').value.toLowerCase();
  const region = document.getElementById('ben-filter-region').value;

  const filtered = allBeneficiaries.filter(b => {
    const matchesSearch = b.name.toLowerCase().includes(search) || 
                          b.beneficiary_id.toLowerCase().includes(search) ||
                          (b.ration_card_number && b.ration_card_number.toLowerCase().includes(search));
    const matchesRegion = !region || b.region === region;
    return matchesSearch && matchesRegion;
  });

  renderBeneficiariesTable(filtered);
}

async function deleteBeneficiaryItem(bid) {
  if (!confirm(`Are you sure you want to delete beneficiary ${bid}?`)) return;
  try {
    const res = await API.deleteBeneficiary(bid);
    if (res && res.status === 'success') {
      showToast(`Beneficiary ${bid} deleted`, 'info');
      await fetchBeneficiaries();
    }
  } catch (err) {
    showToast(err.message || 'Error deleting beneficiary', 'error');
  }
}
