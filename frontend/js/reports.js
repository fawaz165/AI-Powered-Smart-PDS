/**
 * AI-Powered Smart PDS - Reports Export Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  setupReportFilters();
});

function setupReportFilters() {
  // Leave date inputs blank by default so exports encompass full historical database scope
  // If the user specifies dates, they will be applied automatically
  updateExportLinks();
}

function updateExportLinks() {
  const district = document.getElementById('filter-report-district')?.value || 'ALL';
  const commodity = document.getElementById('filter-report-commodity')?.value || 'ALL';
  const startDate = document.getElementById('filter-report-start-date')?.value || '';
  const endDate = document.getElementById('filter-report-end-date')?.value || '';
  const risk = document.getElementById('filter-report-risk')?.value || 'ALL';

  // Build common query params
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
    if (commodity !== 'ALL') fraudParams.append('commodity', commodity);
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
    else if (startDate) filters.push(`From ${startDate}`);
    else if (endDate) filters.push(`Up to ${endDate}`);
    
    if (filters.length > 0) {
      statusBadge.innerHTML = `<i class="fa-solid fa-filter"></i> Filters Active: ${filters.join(' &bull; ')}`;
      statusBadge.className = 'badge badge-warning';
    } else {
      statusBadge.innerHTML = '<i class="fa-solid fa-earth-americas"></i> All Districts &bull; Full Database Scope';
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
  if (startDate) startDate.value = '';
  if (endDate) endDate.value = '';

  updateExportLinks();
  if (typeof showToast === 'function') {
    showToast('Filters reset to full database scope', 'info');
  }
}

function triggerDownloadNotify(reportName) {
  if (typeof showToast === 'function') {
    showToast(`Generating ${reportName} spreadsheet from live MongoDB records...`, 'success');
  }
}
