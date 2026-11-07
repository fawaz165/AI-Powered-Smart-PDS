/**
 * AI-Powered Smart PDS - Bilingual Localization Module (English & Tamil)
 * Non-disruptive, lightweight client-side translation engine.
 */

const I18N_DICTIONARY = {
  en: {
    // Navigation
    "nav.dashboard": "Dashboard",
    "nav.beneficiaries": "Beneficiaries",
    "nav.commodities": "Commodities",
    "nav.inventory": "Inventory Stock",
    "nav.transactions": "Transactions",
    "nav.predictions": "Demand Forecast",
    "nav.fraud": "Fraud & Anomalies",
    "nav.reports": "Reports & Exports",
    "nav.about": "System Architecture",
    "nav.logout": "Sign Out",

    // Roles
    "role.admin": "System Admin",
    "role.officer": "District Officer",
    "role.dealer": "FPS Dealer",

    // Common Commodities
    "commodity.rice": "Rice",
    "commodity.wheat": "Wheat",
    "commodity.sugar": "Sugar",
    "commodity.dal": "Dal",

    // KPI & Status Labels
    "kpi.cardholders": "Cardholders",
    "kpi.stock": "Warehouse Stock",
    "kpi.demand": "Predicted Demand",
    "kpi.procurement": "Procurement Required",
    "kpi.shortage": "Shortage",
    "kpi.sufficient": "Sufficient Stock",
    "status.pending_review": "Pending Review",
    "status.verified_legitimate": "Verified Legitimate",
    "status.confirmed_irregularity": "Confirmed Irregularity",

    // Action Buttons & Titles
    "btn.record_distribution": "Record Distribution",
    "btn.calculate_forecast": "Calculate Demand & Procurement",
    "btn.review_alert": "Review Alert",
    "btn.download_excel": "Download Excel",
    "btn.reset_filters": "Reset Filters"
  },
  ta: {
    // Navigation
    "nav.dashboard": "முகப்பு பலகை",
    "nav.beneficiaries": "பயனாளிகள் பட்டியல்",
    "nav.commodities": "உணவுப் பொருட்கள்",
    "nav.inventory": "சரக்கு இருப்பு",
    "nav.transactions": "விநியோகப் பதிவு",
    "nav.predictions": "தேவை கணிப்பு",
    "nav.fraud": "மோசடி ஆய்வு",
    "nav.reports": "அறிக்கைகள்",
    "nav.about": "கட்டமைப்பு",
    "nav.logout": "வெளியேறு",

    // Roles
    "role.admin": "முதன்மை நிர்வாகி",
    "role.officer": "மாவட்ட அதிகாரி",
    "role.dealer": "நியாயவிலைக் கடை விற்பனையாளர்",

    // Common Commodities
    "commodity.rice": "அரிசி",
    "commodity.wheat": "கோதுமை",
    "commodity.sugar": "சர்க்கரை",
    "commodity.dal": "பருப்பு",

    // KPI & Status Labels
    "kpi.cardholders": "குடும்ப அட்டைதாரர்கள்",
    "kpi.stock": "கிடங்கு இருப்பு",
    "kpi.demand": "கணிக்கப்பட்ட தேவை",
    "kpi.procurement": "தேவைப்படும் கொள்முதல்",
    "kpi.shortage": "பற்றாக்குறை",
    "kpi.sufficient": "போதுமான இருப்பு",
    "status.pending_review": "ஆய்வு நிலுவையில்",
    "status.verified_legitimate": "சரிபார்க்கப்பட்டது",
    "status.confirmed_irregularity": "முறைக்கேடு உறுதி",

    // Action Buttons & Titles
    "btn.record_distribution": "தானிய விநியோகம் செய்",
    "btn.calculate_forecast": "தேவை & கொள்முதலைக் கணக்கிடு",
    "btn.review_alert": "ஆய்வு செய்",
    "btn.download_excel": "எக்செல் பதிவிறக்கு",
    "btn.reset_filters": "வடிப்பான்களை மீட்டமை"
  }
};

const I18n = {
  getLanguage() {
    return localStorage.getItem('smart_pds_lang') || 'en';
  },

  setLanguage(lang) {
    if (lang !== 'en' && lang !== 'ta') lang = 'en';
    localStorage.setItem('smart_pds_lang', lang);
    this.applyTranslations();
    this.updateTogglePill();
  },

  toggleLanguage() {
    const current = this.getLanguage();
    this.setLanguage(current === 'en' ? 'ta' : 'en');
  },

  t(key, fallback = '') {
    const lang = this.getLanguage();
    return (I18N_DICTIONARY[lang] && I18N_DICTIONARY[lang][key]) || 
           (I18N_DICTIONARY.en && I18N_DICTIONARY.en[key]) || 
           fallback || key;
  },

  applyTranslations() {
    const lang = this.getLanguage();
    document.documentElement.lang = lang;

    // Translate elements marked with data-i18n
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const translation = this.t(key);
      if (translation) {
        if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit')) {
          el.value = translation;
        } else {
          el.textContent = translation;
        }
      }
    });

    // Translate navigation sidebar links
    const navMap = {
      'dashboard.html': 'nav.dashboard',
      'beneficiaries.html': 'nav.beneficiaries',
      'commodities.html': 'nav.commodities',
      'inventory.html': 'nav.inventory',
      'transactions.html': 'nav.transactions',
      'predictions.html': 'nav.predictions',
      'fraud.html': 'nav.fraud',
      'reports.html': 'nav.reports',
      'about.html': 'nav.about'
    };

    document.querySelectorAll('.sidebar-menu a').forEach(a => {
      const href = a.getAttribute('href');
      if (href && navMap[href]) {
        const span = a.querySelector('span');
        if (span) {
          span.textContent = this.t(navMap[href], span.textContent);
        }
      }
    });
  },

  updateTogglePill() {
    const lang = this.getLanguage();
    const btn = document.getElementById('btn-i18n-toggle');
    if (btn) {
      if (lang === 'ta') {
        btn.innerHTML = `<i class="fa-solid fa-language"></i> தமிழ் (TA)`;
        btn.title = "Switch to English";
      } else {
        btn.innerHTML = `<i class="fa-solid fa-language"></i> English (EN)`;
        btn.title = "தமிழுக்கு மாறுக";
      }
    }
  },

  mountLanguageToggle() {
    if (document.getElementById('btn-i18n-toggle')) return;

    // Look for top header or actions container
    const target = document.querySelector('.header-right') || document.querySelector('.nav-actions') || document.querySelector('.top-nav');
    if (!target) return;

    const btn = document.createElement('button');
    btn.id = 'btn-i18n-toggle';
    btn.className = 'btn btn-secondary btn-sm';
    btn.style.marginRight = '8px';
    btn.style.fontSize = '0.78rem';
    btn.style.padding = '6px 10px';
    btn.style.display = 'inline-flex';
    btn.style.alignItems = 'center';
    btn.style.gap = '6px';
    btn.onclick = () => this.toggleLanguage();

    target.insertBefore(btn, target.firstChild);
    this.updateTogglePill();
  },

  init() {
    this.mountLanguageToggle();
    this.applyTranslations();
  }
};

document.addEventListener('DOMContentLoaded', () => {
  I18n.init();
});

