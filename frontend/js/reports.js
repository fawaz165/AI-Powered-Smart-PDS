/**
 * AI-Powered Smart PDS - Reports Export Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  setupReportFilters();
});

function setupReportFilters() {
  const districtSelect = document.getElementById('filter-report-district');
  const commoditySelect = document.getElementById('filter-report-commodity');
  const startDateInput = document.getElementById('filter-report-start-date');
  const endDateInput = document.getElementById('filter-report-end-date');
  const riskSelect = document.getElementById('filter-report-risk');

  // Set default dates to current month range
  const now = new Date();
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
  const today = now.toISOString().split('T')[0];
  if (startDateInput && !startDateInput.value) startDateInput.value = firstDay;
  if (endDateInput && !endDateInput.value) endDateInput.value = today;

  updateExportLinks();
}

function updateExportLinks() {
  const district = document.getElementById('filter-report-district')?.value || 'ALL';
  const commodity = document.getElementById('filter-report-commodity')?.value || 'ALL';
  const startDate = document.getElementById('filter-report-start-date')?.value || '';
  const endDate = document.getElementById('filter-report-end-date')?.value || '';
  const risk = document.getElementById('filter-report-risk')?.value || 'ALL';

  // Build query params
  const commonParams = new URLSearchParams();
  if (district !== 'ALL') commonParams.append('region', district);
  if (commodity !== 'ALL') commonParams.append('commodity', commodity);

  // 1. Inventory Report Link
  const invLink = document.getElementById('btn-export-inventory');
  if (invLink) {
    const invParams = new URLSearchParams(commonParams);
    invLink.href = `/api/reports/inventory?${invParams.toString()}`;
  }

  // 2. Distribution Report Link
  const distLink = document.getElementById('btn-export-distribution');
  if (distLink) {
    const distParams = new URLSearchParams(commonParams);
    if (startDate) distParams.append('start_date', startDate);
    if (endDate) distParams.append('end_date', endDate);
    if (risk !== 'ALL') distParams.append('risk_level', risk);
    distLink.href = `/api/reports/distribution?${distParams.toString()}`;
  }

  // 3. Predictions Report Link
  const predLink = document.getElementById('btn-export-predictions');
  if (predLink) {
    const predParams = new URLSearchParams(commonParams);
    predLink.href = `/api/reports/predictions?${predParams.toString()}`;
  }

  // 4. Fraud Report Link
  const fraudLink = document.getElementById('btn-export-fraud');
  if (fraudLink) {
    const fraudParams = new URLSearchParams();
    if (district !== 'ALL') fraudParams.append('region', district);
    if (risk !== 'ALL') fraudParams.append('risk_level', risk);
    if (startDate) fraudParams.append('start_date', startDate);
    if (endDate) fraudParams.append('end_date', endDate);
    fraudLink.href = `/api/reports/fraud?${fraudParams.toString()}`;
  }

  // Update filter status badge
  const statusBadge = document.getElementById('active-filters-badge');
  if (statusBadge) {
    const filters = [];
    if (district !== 'ALL') filters.push(district);
    if (commodity !== 'ALL') filters.push(commodity);
    if (risk !== 'ALL') filters.push(`${risk} Risk`);
    if (startDate && endDate) filters.push(`${startDate} to ${endDate}`);
    
    if (filters.length > 0) {
      statusBadge.innerHTML = `<i class="fa-solid fa-filter"></i> Filters Active: ${filters.join(' &bull; ')}`;
      statusBadge.className = 'badge badge-warning';
    } else {
      statusBadge.innerHTML = '<i class="fa-solid fa-earth-americas"></i> All Districts &bull; Full Database Range';
      statusBadge.className = 'badge badge-info';
    }
  }
}

function resetReportFilters() {
  const district = document.getElementById('filter-report-district');
  const commodity = document.getElementById('filter-report-commodity');
  const startDate = document.getElementById('filter-report-start-date');
  const endDate = document.getElementById('filter-report-end-date');
  const risk = document.getElementById('filter-report-risk');

  if (district) district.value = 'ALL';
  if (commodity) commodity.value = 'ALL';
  if (risk) risk.value = 'ALL';
  
  const now = new Date();
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
  const today = now.toISOString().split('T')[0];
  if (startDate) startDate.value = firstDay;
  if (endDate) endDate.value = today;

  updateExportLinks();
  showToast('Filters reset to default scope', 'info');
}

function triggerDownloadNotify(reportName) {
  showToast(`Generating ${reportName} spreadsheet from live MongoDB records...`, 'success');
}
