/**
 * AI-Powered Smart PDS - Core Frontend API Client & UI Helpers
 */

const API_BASE = '/api';

const API = {
  getToken() {
    return localStorage.getItem('smart_pds_token');
  },

  getUser() {
    const raw = localStorage.getItem('smart_pds_user');
    return raw ? JSON.parse(raw) : null;
  },

  setAuth(token, user) {
    localStorage.setItem('smart_pds_token', token);
    localStorage.setItem('smart_pds_user', JSON.stringify(user));
  },

  clearAuth() {
    localStorage.removeItem('smart_pds_token');
    localStorage.removeItem('smart_pds_user');
  },

  async request(endpoint, options = {}) {
    const headers = options.headers || {};
    const token = this.getToken();

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    options.headers = headers;

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, options);
      
      // Auto-handle 401 Unauthorized
      if (response.status === 401 && !window.location.pathname.endsWith('index.html') && window.location.pathname !== '/') {
        this.clearAuth();
        window.location.href = 'index.html';
        return null;
      }

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP error ${response.status}`);
      }
      return data;
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  // Auth
  login(username, password) {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    });
  },

  // Beneficiaries
  getBeneficiaries(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/beneficiaries?${query}`);
  },

  getBeneficiary(id) {
    return this.request(`/beneficiaries/${id}`);
  },

  createBeneficiary(payload) {
    return this.request('/beneficiaries', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  updateBeneficiary(id, payload) {
    return this.request(`/beneficiaries/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  },

  deleteBeneficiary(id) {
    return this.request(`/beneficiaries/${id}`, {
      method: 'DELETE'
    });
  },

  // Commodities
  getCommodities() {
    return this.request('/commodities');
  },

  createCommodity(payload) {
    return this.request('/commodities', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  // Inventory
  getInventory(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/inventory?${query}`);
  },

  getInventoryAlerts() {
    return this.request('/inventory/alerts');
  },

  updateInventoryStock(commodity, region, current_stock) {
    return this.request('/inventory/update-stock', {
      method: 'PUT',
      body: JSON.stringify({ commodity, region, current_stock })
    });
  },

  // Transactions
  getTransactions(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/transactions?${query}`);
  },

  distributeGrain(payload) {
    return this.request('/transactions', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  getFraudAlerts() {
    return this.request('/transactions/fraud-alerts');
  },

  // ML Intelligence
  predictDemand(payload) {
    return this.request('/predict-demand', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  detectAnomaly(payload) {
    return this.request('/detect-anomaly', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  getModelMetrics() {
    return this.request('/model-metrics');
  },

  getAnomalyMetrics() {
    return this.request('/anomaly-metrics');
  }
};

// UI Notification System
function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${message}</span>
    <button style="background:none; border:none; color:#fff; cursor:pointer; margin-left:12px;" onclick="this.parentElement.remove()">&times;</button>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 4500);
}

// Modal Helpers
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add('active');
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove('active');
}

// Global Nav Active Highlighter & Auth Guard
document.addEventListener('DOMContentLoaded', () => {
  const path = window.location.pathname.split('/').pop() || 'index.html';
  
  // Highlight active link
  const navLinks = document.querySelectorAll('.nav-link');
  navLinks.forEach(link => {
    if (link.getAttribute('href') === path) {
      link.classList.add('active');
    }
  });

  // Check auth on protected pages
  if (path !== 'index.html' && path !== '' && !path.endsWith('index.html')) {
    const user = API.getUser();
    if (!user) {
      window.location.href = 'index.html';
    } else {
      const userElem = document.getElementById('sidebar-user-name');
      if (userElem) userElem.textContent = user.full_name || user.username;
      const roleElem = document.getElementById('sidebar-user-role');
      if (roleElem) roleElem.textContent = (user.role || 'Officer').toUpperCase();
    }
  }
});

function handleLogout() {
  API.clearAuth();
  showToast('Logged out successfully', 'info');
  setTimeout(() => {
    window.location.href = 'index.html';
  }, 400);
}
