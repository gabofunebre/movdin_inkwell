import {
  fetchAccounts,
  fetchTransactions,
  createTransaction,
  fetchFrequents,
  updateTransaction,
  deleteTransaction,
  syncBillingTransactions,
  fetchNotifications,
  acknowledgeNotification
} from './api.js?v=3';
import {
  renderTransaction,
  populateAccounts,
  showOverlay,
  hideOverlay,
} from './ui.js?v=2';
import { sanitizeDecimalInput, parseDecimal, formatCurrency } from './money.js?v=1';
import { createFilterSummaryManager } from './filterSummary.js?v=1';

const tbody = document.querySelector('#tx-table tbody');
const container = document.getElementById('table-container');
const modalEl = document.getElementById('txModal');
const txModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('tx-form');
const alertBox = document.getElementById('tx-alert');
const searchBox = document.getElementById('search-box');
const filterButton = document.getElementById('tx-filter-button');
const filterModalEl = document.getElementById('txFilterModal');
const filterModal = filterModalEl ? new bootstrap.Modal(filterModalEl) : null;
const filterForm = document.getElementById('tx-filter-form');
const filterAccountSelect = filterForm?.elements['filter_account_id'] || null;
const filterAlert = document.getElementById('tx-filter-alert');
const clearFiltersBtn = document.getElementById('tx-clear-filters');
const filterSummary = document.getElementById('tx-filter-summary');
const filterSummaryItems = document.getElementById('tx-filter-summary-items');
const filterSummaryClear = document.getElementById('tx-filter-summary-clear');
const filterSummaryManager = createFilterSummaryManager({
  container: filterSummary,
  itemsContainer: filterSummaryItems,
  clearButton: filterSummaryClear,
  onClear: () => clearTransactionFilters()
});
const headers = document.querySelectorAll('#tx-table thead th.sortable');
const freqCheck = document.getElementById('freq-check');
const freqSelect = document.getElementById('freq-select');
const descInput = document.getElementById('desc-input');
const amountInput = form.amount;
const billingSyncButton = document.getElementById('billing-sync-button');
const billingSyncLabel = document.getElementById('billing-sync-button-label');
const billingNotificationBadgeContainer = document.getElementById('billing-notification-badges');

const BILLING_NOTIFICATION_EVENT_TYPES = ['created', 'updated', 'deleted'];
const billingNotificationBadges = Object.fromEntries(
  BILLING_NOTIFICATION_EVENT_TYPES.map(type => [
    type,
    billingNotificationBadgeContainer?.querySelector(`[data-type="${type}"]`) || null
  ])
);

const BILLING_NOTIFICATION_TYPE = 'movimiento_cta_facturacion_iw';
const BILLING_NOTIFICATION_PAGE_LIMIT = 100;
const BILLING_NOTIFICATION_MAX_PAGES = 20;
const BILLING_NOTIFICATION_REFRESH_INTERVAL_MS = 60000;
const BILLING_NOTIFICATION_BADGE_MAX = 99;

function createEmptyEventCounts() {
  return BILLING_NOTIFICATION_EVENT_TYPES.reduce((acc, type) => {
    acc[type] = 0;
    return acc;
  }, {});
}

function normalizeEventCounts(counts) {
  const normalized = createEmptyEventCounts();
  if (!counts || typeof counts !== 'object') {
    return normalized;
  }
  for (const type of BILLING_NOTIFICATION_EVENT_TYPES) {
    const value = counts[type];
    normalized[type] = Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
  }
  return normalized;
}

function getBillingEventSummaryLines(counts) {
  const normalized = normalizeEventCounts(counts);
  return [
    `nuevos registros: ${normalized.created || 0}`,
    `modificaciones: ${normalized.updated || 0}`,
    `eliminaciones: ${normalized.deleted || 0}`
  ];
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, match => {
    switch (match) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      case "'":
        return '&#39;';
      default:
        return match;
    }
  });
}

function pickEventCounts(source) {
  if (!source || typeof source !== 'object') return null;
  const counts = createEmptyEventCounts();
  let hasData = false;
  for (const type of BILLING_NOTIFICATION_EVENT_TYPES) {
    if (Object.prototype.hasOwnProperty.call(source, type)) {
      const value = source[type];
      counts[type] = Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
      hasData = true;
    }
  }
  return hasData ? counts : null;
}

function extractEventCountsFromPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const candidates = [
    payload.notification_counts,
    payload.notifications?.event_counts,
    payload.notifications?.counts,
    payload.notifications,
    payload.event_counts,
    payload.counts,
    payload.summary
  ];
  for (const candidate of candidates) {
    const extracted = pickEventCounts(candidate);
    if (extracted) {
      return extracted;
    }
  }
  return pickEventCounts(payload);
}

let billingNotificationState = {
  ids: [],
  unreadCount: 0,
  eventCounts: createEmptyEventCounts()
};
let billingNotificationTimer = null;

let billingSyncOriginalLabel = '';
if (billingSyncLabel) {
  billingSyncOriginalLabel = billingSyncLabel.textContent.trim();
} else if (billingSyncButton) {
  billingSyncOriginalLabel = billingSyncButton.textContent.trim();
}

if (billingSyncButton) {
  if (billingSyncOriginalLabel) {
    billingSyncButton.setAttribute('aria-label', billingSyncOriginalLabel);
  }
  billingSyncButton.setAttribute('data-notification-count', '0');
}

let offset = 0;
const limit = 50;
let loading = false;
let accounts = [];
let accountMap = {};
let transactions = [];
let sortColumn = 0;
let sortAsc = false;
let frequents = [];
let frequentMap = {};
const filterState = {
  startDate: '',
  endDate: '',
  accountId: ''
};

function formatFilterDate(value) {
  if (!value) return '';
  const parts = value.split('-');
  if (parts.length !== 3) return value;
  const [year, month, day] = parts;
  return `${day}/${month}/${year}`;
}

function getAccountLabel(accountId) {
  if (!accountId) return '';
  const account = accountMap?.[accountId];
  if (account?.name) {
    return account.name;
  }
  return `#${accountId}`;
}

function updateFilterSummary() {
  const chips = [];
  if (filterState.startDate) {
    chips.push({ label: 'Desde', value: formatFilterDate(filterState.startDate) });
  }
  if (filterState.endDate) {
    chips.push({ label: 'Hasta', value: formatFilterDate(filterState.endDate) });
  }
  if (filterState.accountId) {
    chips.push({ label: 'Cuenta', value: getAccountLabel(filterState.accountId) });
  }

  filterSummaryManager.update(chips);
}

function clearTransactionFilters() {
  if (filterForm) {
    filterForm.reset();
  }
  filterState.startDate = '';
  filterState.endDate = '';
  filterState.accountId = '';
  hideFilterAlert();
  if (filterModal) {
    filterModal.hide();
  }
  renderTransactions();
}

function renderTransactions() {
  const q = searchBox.value.trim().toLowerCase();
  const startDate = filterState.startDate ? new Date(filterState.startDate) : null;
  const endDate = filterState.endDate ? new Date(filterState.endDate) : null;
  const accountId = filterState.accountId;
  const filtered = transactions.filter(tx => {
    const txDate = new Date(tx.date);
    if (startDate && txDate < startDate) {
      return false;
    }
    if (endDate && txDate > endDate) {
      return false;
    }
    if (accountId && String(tx.account_id) !== accountId) {
      return false;
    }
    const accName = accountMap[tx.account_id]?.name.toLowerCase() || '';
    return tx.description.toLowerCase().includes(q) || accName.includes(q);
  });
  filtered.sort((a, b) => {
    switch (sortColumn) {
      case 0:
        return sortAsc
          ? new Date(a.date) - new Date(b.date)
          : new Date(b.date) - new Date(a.date);
      case 1:
        return sortAsc
          ? a.description.localeCompare(b.description)
          : b.description.localeCompare(a.description);
      case 2:
        return sortAsc ? a.amount - b.amount : b.amount - a.amount;
      case 3:
        const accA = accountMap[a.account_id]?.name || '';
        const accB = accountMap[b.account_id]?.name || '';
        return sortAsc ? accA.localeCompare(accB) : accB.localeCompare(accA);
      default:
        return 0;
    }
  });
  tbody.innerHTML = '';
  filtered.forEach(tx => renderTransaction(tbody, tx, accountMap, openEditModal, confirmDelete));
  updateFilterSummary();
}

async function loadMore() {
  if (loading) return;
  loading = true;
  const data = await fetchTransactions(limit, offset);
  transactions = transactions.concat(data);
  offset += data.length;
  renderTransactions();
  loading = false;
}

function openModal(type) {
  form.reset();
  amountInput.value = '';
  document.getElementById('form-title').textContent = type === 'income' ? 'Nuevo Ingreso' : 'Nuevo Egreso';
  const availableAccounts = accounts.filter(a => a.is_active && !a.is_billing);
  populateAccounts(form.account_id, availableAccounts);
  form.account_id.disabled = availableAccounts.length === 0;
  form.dataset.type = type;
  form.dataset.mode = 'create';
  delete form.dataset.id;
  alertBox.classList.add('d-none');
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  form.date.value = today;
  freqCheck.checked = false;
  descInput.classList.remove('d-none');
  freqSelect.classList.add('d-none');
  txModal.show();
}

function openEditModal(tx) {
  form.reset();
  const isIncome = tx.amount >= 0;
  document.getElementById('form-title').textContent = isIncome ? 'Editar Ingreso' : 'Editar Egreso';
  const availableAccounts = accounts.filter(
    a =>
      a.is_active && (!a.is_billing || a.id === tx.account_id)
  );
  populateAccounts(form.account_id, availableAccounts, tx.account_id);
  form.account_id.disabled = availableAccounts.length === 0;
  form.dataset.type = isIncome ? 'income' : 'expense';
  form.dataset.mode = 'edit';
  form.dataset.id = tx.id;
  alertBox.classList.add('d-none');
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  form.date.value = tx.date;
  freqCheck.checked = false;
  descInput.classList.remove('d-none');
  freqSelect.classList.add('d-none');
  descInput.value = tx.description;
  amountInput.value = formatCurrency(Math.abs(tx.amount));
  form.account_id.value = tx.account_id;
  txModal.show();
}

async function confirmDelete(tx) {
  const confirmed = await showConfirmModal('¿Eliminar movimiento?', {
    confirmText: 'Eliminar'
  });
  if (!confirmed) return;
  showOverlay();
  const result = await deleteTransaction(tx.id);
  hideOverlay();
  if (result.ok) {
    transactions = [];
    offset = 0;
    await loadMore();
  } else {
    showAlertModal(result.error || 'Error al eliminar', {
      title: 'Error',
      confirmClass: 'btn-danger'
    });
  }
}

document.getElementById('add-income').addEventListener('click', () => openModal('income'));
document.getElementById('add-expense').addEventListener('click', () => openModal('expense'));
searchBox.addEventListener('input', renderTransactions);
if (filterButton && filterModal && filterForm) {
  filterButton.addEventListener('click', () => {
    const today = new Date().toISOString().split('T')[0];
    if (filterForm.start_date) {
      filterForm.start_date.max = today;
      filterForm.start_date.value = filterState.startDate || '';
    }
    if (filterForm.end_date) {
      filterForm.end_date.max = today;
      filterForm.end_date.value = filterState.endDate || '';
    }
    populateFilterAccounts(filterState.accountId);
    hideFilterAlert();
    filterModal.show();
  });
}

if (filterForm) {
  filterForm.addEventListener('submit', event => {
    event.preventDefault();
    const startDate = filterForm.start_date?.value || '';
    const endDate = filterForm.end_date?.value || '';
    if (startDate && endDate && startDate > endDate) {
      showFilterAlert('La fecha inicio no puede ser posterior a la fecha fin');
      return;
    }
    filterState.startDate = startDate;
    filterState.endDate = endDate;
    filterState.accountId = filterForm.filter_account_id?.value || '';
    hideFilterAlert();
    if (filterModal) {
      filterModal.hide();
    }
    renderTransactions();
  });
}

if (clearFiltersBtn) {
  clearFiltersBtn.addEventListener('click', () => {
    clearTransactionFilters();
  });
}

freqCheck.addEventListener('change', () => {
  if (freqCheck.checked) {
    populateFreqSelect();
    descInput.classList.add('d-none');
    freqSelect.classList.remove('d-none');
    if (freqSelect.value) {
      applyFrequent(frequentMap[freqSelect.value]);
    }
  } else {
    descInput.classList.remove('d-none');
    freqSelect.classList.add('d-none');
  }
});

freqSelect.addEventListener('change', () => {
  const f = frequentMap[freqSelect.value];
  if (f) applyFrequent(f);
});

function populateFreqSelect() {
  freqSelect.innerHTML = '';
  frequents.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.id;
    opt.textContent = f.description;
    freqSelect.appendChild(opt);
  });
}

function applyFrequent(f) {
  if (!f) return;
  descInput.value = f.description;
}

function populateFilterAccounts(selected = '') {
  if (!filterAccountSelect) return;
  filterAccountSelect.innerHTML = '';
  const allOption = document.createElement('option');
  allOption.value = '';
  allOption.textContent = 'Todas';
  filterAccountSelect.appendChild(allOption);
  const availableAccounts = accounts.filter(a => a.is_active);
  availableAccounts
    .sort((a, b) => a.name.localeCompare(b.name))
    .forEach(account => {
      const option = document.createElement('option');
      option.value = String(account.id);
      option.textContent = account.name;
      if (selected && option.value === selected) {
        option.selected = true;
      }
      filterAccountSelect.appendChild(option);
    });
}

function hideFilterAlert() {
  if (!filterAlert) return;
  filterAlert.classList.add('d-none');
  filterAlert.textContent = '';
}

function showFilterAlert(message) {
  if (!filterAlert) return;
  filterAlert.textContent = message;
  filterAlert.classList.remove('d-none');
}

function updateBillingNotificationBadges(state) {
  if (!billingNotificationBadgeContainer || !billingSyncButton) return;
  const counts = normalizeEventCounts(state?.eventCounts);
  const totalFromCounts = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const total = Number.isFinite(state?.unreadCount)
    ? Math.max(totalFromCounts, Math.max(0, Math.trunc(state.unreadCount)))
    : totalFromCounts;
  billingSyncButton.setAttribute('data-notification-count', String(total));

  let hasVisibleBadge = false;
  for (const type of BILLING_NOTIFICATION_EVENT_TYPES) {
    const badge = billingNotificationBadges[type];
    if (!badge) continue;
    const count = counts[type] || 0;
    if (count > 0) {
      const displayValue =
        count > BILLING_NOTIFICATION_BADGE_MAX
          ? `${BILLING_NOTIFICATION_BADGE_MAX}+`
          : String(count);
      badge.textContent = displayValue;
      badge.classList.remove('d-none');
      hasVisibleBadge = true;
    } else {
      badge.textContent = '';
      badge.classList.add('d-none');
    }
  }

  if (hasVisibleBadge) {
    billingNotificationBadgeContainer.classList.remove('d-none');
    billingNotificationBadgeContainer.setAttribute('aria-hidden', 'false');
  } else {
    billingNotificationBadgeContainer.classList.add('d-none');
    billingNotificationBadgeContainer.setAttribute('aria-hidden', 'true');
  }

  if (billingSyncOriginalLabel) {
    const summaryLines = getBillingEventSummaryLines(counts);
    const detailText = summaryLines.join(', ');
    const ariaLabel = total > 0 ? `${billingSyncOriginalLabel} (${detailText})` : billingSyncOriginalLabel;
    billingSyncButton.setAttribute('aria-label', ariaLabel);
    if (total > 0) {
      billingSyncButton.title = `Pendientes de sincronizar — ${summaryLines.join(' · ')}`;
    } else {
      billingSyncButton.removeAttribute('title');
    }
  }
}

function stopBillingNotificationRefreshTimer() {
  if (billingNotificationTimer) {
    clearTimeout(billingNotificationTimer);
    billingNotificationTimer = null;
  }
}

function scheduleBillingNotificationRefresh() {
  if (!billingSyncButton || !billingNotificationBadgeContainer) return;
  stopBillingNotificationRefreshTimer();
  billingNotificationTimer = setTimeout(() => {
    refreshBillingNotificationIndicator().catch(error => {
      console.error('Error al actualizar las notificaciones de facturación', error);
    });
  }, BILLING_NOTIFICATION_REFRESH_INTERVAL_MS);
}

async function fetchBillingNotificationState() {
  const ids = [];
  let unreadCount = 0;
  const eventCounts = createEmptyEventCounts();
  let cursor = null;
  let first = true;
  let iterations = 0;

  while (true) {
    const options = {
      status: 'unread',
      type: BILLING_NOTIFICATION_TYPE,
      limit: BILLING_NOTIFICATION_PAGE_LIMIT
    };
    if (cursor) options.cursor = cursor;
    if (first) options.include = 'unread_count';

    const response = await fetchNotifications(options);

    if (first) {
      if (typeof response.unread_count === 'number' && Number.isFinite(response.unread_count)) {
        unreadCount = Math.max(0, response.unread_count);
      } else {
        unreadCount = 0;
      }
      first = false;
    }

    if (Array.isArray(response.items)) {
      response.items.forEach(item => {
        if (item && item.id) {
          ids.push(item.id);
          const eventType = item.variables?.event;
          if (typeof eventType === 'string') {
            const normalized = eventType.toLowerCase();
            if (Object.prototype.hasOwnProperty.call(eventCounts, normalized)) {
              eventCounts[normalized] += 1;
            }
          }
        }
      });
    }

    const nextCursor = response.cursor || null;
    iterations += 1;
    if (!nextCursor || nextCursor === cursor || iterations >= BILLING_NOTIFICATION_MAX_PAGES) {
      break;
    }
    cursor = nextCursor;
  }

  const totalFromCounts = Object.values(eventCounts).reduce((sum, value) => sum + value, 0);
  if (!Number.isFinite(unreadCount) || unreadCount < totalFromCounts) {
    unreadCount = totalFromCounts;
  }

  return { ids, unreadCount, eventCounts };
}

async function refreshBillingNotificationIndicator() {
  if (!billingSyncButton || !billingNotificationBadgeContainer) return;
  stopBillingNotificationRefreshTimer();
  try {
    const state = await fetchBillingNotificationState();
    const eventCounts = normalizeEventCounts(state.eventCounts);
    const totalFromCounts = Object.values(eventCounts).reduce((sum, value) => sum + value, 0);
    const count = Number.isFinite(state.unreadCount)
      ? Math.max(totalFromCounts, Math.max(0, Math.trunc(state.unreadCount)))
      : Math.max(totalFromCounts, state.ids.length);
    billingNotificationState = {
      ids: state.ids,
      unreadCount: count,
      eventCounts
    };
    updateBillingNotificationBadges(billingNotificationState);
  } catch (error) {
    console.error('Error al obtener las notificaciones de facturación', error);
  } finally {
    scheduleBillingNotificationRefresh();
  }
}

async function markBillingNotificationsAsRead() {
  if (!billingSyncButton || !billingNotificationBadgeContainer) return;
  stopBillingNotificationRefreshTimer();

  if (!billingNotificationState.ids.length) {
    try {
      const state = await fetchBillingNotificationState();
      const eventCounts = normalizeEventCounts(state.eventCounts);
      const totalFromCounts = Object.values(eventCounts).reduce((sum, value) => sum + value, 0);
      const count = Number.isFinite(state.unreadCount)
        ? Math.max(totalFromCounts, Math.max(0, Math.trunc(state.unreadCount)))
        : Math.max(totalFromCounts, state.ids.length);
      billingNotificationState = {
        ids: state.ids,
        unreadCount: count,
        eventCounts
      };
      updateBillingNotificationBadges(billingNotificationState);
    } catch (error) {
      console.error('Error al preparar las notificaciones de facturación para confirmar', error);
      scheduleBillingNotificationRefresh();
      return;
    }
  }

  if (!billingNotificationState.ids.length) {
    updateBillingNotificationBadges({
      ids: [],
      unreadCount: 0,
      eventCounts: createEmptyEventCounts()
    });
    scheduleBillingNotificationRefresh();
    return;
  }

  let hadError = false;
  for (const id of billingNotificationState.ids) {
    try {
      const result = await acknowledgeNotification(id);
      if (!result.ok) {
        hadError = true;
        if (result.error) {
          console.error('No se pudo confirmar la notificación de facturación', result.error);
        }
      }
    } catch (error) {
      console.error('Error al confirmar una notificación de facturación', error);
      hadError = true;
    }
  }

  if (hadError) {
    await refreshBillingNotificationIndicator();
    return;
  }

  billingNotificationState = {
    ids: [],
    unreadCount: 0,
    eventCounts: createEmptyEventCounts()
  };
  updateBillingNotificationBadges(billingNotificationState);
  scheduleBillingNotificationRefresh();
}

amountInput.addEventListener('input', () => {
  sanitizeDecimalInput(amountInput);
});

amountInput.addEventListener('blur', () => {
  if (!amountInput.value.trim()) return;
  const value = Math.abs(parseDecimal(amountInput.value));
  amountInput.value = formatCurrency(value);
});

headers.forEach((th, index) => {
  th.addEventListener('click', () => {
    if (sortColumn === index) {
      sortAsc = !sortAsc;
    } else {
      sortColumn = index;
      sortAsc = true;
    }
    updateSortIcons();
    renderTransactions();
  });
});

function updateSortIcons() {
  headers.forEach((th, index) => {
    const icon = th.querySelector('.sort-icon');
    if (!icon) return;
    icon.classList.remove('bi-arrow-up', 'bi-arrow-down', 'bi-arrow-down-up');
    if (index === sortColumn) {
      icon.classList.add(sortAsc ? 'bi-arrow-up' : 'bi-arrow-down');
    } else {
      icon.classList.add('bi-arrow-down-up');
    }
  });
}

container.addEventListener('scroll', () => {
  if (container.scrollTop + container.clientHeight >= container.scrollHeight - 10) {
    loadMore();
  }
});

form.addEventListener('submit', async e => {
  e.preventDefault();
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  let amount = parseDecimal(data.get('amount'));
  amount = form.dataset.type === 'expense' ? -Math.abs(amount) : Math.abs(amount);
  const payload = {
    date: data.get('date'),
    description: data.get('description'),
    amount,
    notes: '',
    account_id: parseInt(data.get('account_id'), 10)
  };
  const today = new Date().toISOString().split('T')[0];
  if (payload.date > today) {
    alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
    alertBox.classList.add('alert-danger');
    alertBox.textContent = 'La fecha no puede ser futura';
    return;
  }

  showOverlay();
  let result;
  if (form.dataset.mode === 'edit' && form.dataset.id) {
    result = await updateTransaction(form.dataset.id, payload);
  } else {
    result = await createTransaction(payload);
  }
  hideOverlay();
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    alertBox.classList.add('alert-success');
    alertBox.textContent = 'Movimiento guardado';
    transactions = [];
    offset = 0;
    await loadMore();
    setTimeout(() => {
      txModal.hide();
      alertBox.classList.add('d-none');
    }, 1000);
  } else {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = result.error || 'Error al guardar';
  }
});

(async function init() {
  accounts = await fetchAccounts(true);
  accountMap = Object.fromEntries(accounts.map(a => [a.id, a]));
  populateFilterAccounts(filterState.accountId);
  updateFilterSummary();
  frequents = await fetchFrequents();
  frequentMap = Object.fromEntries(frequents.map(f => [f.id, f]));
  await loadMore();
  updateSortIcons();
  if (billingSyncButton && billingNotificationBadgeContainer) {
    updateBillingNotificationBadges(billingNotificationState);
    refreshBillingNotificationIndicator();
  }
})();

if (billingSyncButton) {
  billingSyncButton.addEventListener('click', async () => {
    if (billingSyncButton.disabled) return;
    const initialSummaryLines = getBillingEventSummaryLines(
      billingNotificationState.eventCounts
    );
    if (typeof showAlertModal === 'function') {
      try {
        await showAlertModal(initialSummaryLines.join('\n'), {
          title: 'Movimientos pendientes',
          confirmText: 'Continuar',
          confirmClass: 'btn-primary',
          defaultValue: true
        });
      } catch (error) {
        console.error('No se pudo mostrar el resumen de pendientes', error);
      }
    }

    stopBillingNotificationRefreshTimer();
    billingSyncButton.disabled = true;
    const computedStyle = window.getComputedStyle(billingSyncButton);
    const spinnerColor =
      billingSyncButton.style.color || computedStyle.color || '#0d6efd';
    const spinnerHtml =
      `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true" style="color:${spinnerColor}"></span>` +
      'Sincronizando...';
    if (billingSyncLabel) {
      billingSyncLabel.innerHTML = spinnerHtml;
    } else {
      billingSyncButton.innerHTML = spinnerHtml;
      if (
        billingNotificationBadgeContainer &&
        !billingSyncButton.contains(billingNotificationBadgeContainer)
      ) {
        billingSyncButton.appendChild(billingNotificationBadgeContainer);
      }
    }
    showOverlay();
    const result = await syncBillingTransactions();
    hideOverlay();
    billingSyncButton.disabled = false;
    if (billingSyncLabel) {
      billingSyncLabel.textContent = billingSyncOriginalLabel || billingSyncLabel.textContent;
    } else {
      billingSyncButton.textContent = billingSyncOriginalLabel || billingSyncButton.textContent;
      if (
        billingNotificationBadgeContainer &&
        !billingSyncButton.contains(billingNotificationBadgeContainer)
      ) {
        billingSyncButton.appendChild(billingNotificationBadgeContainer);
      }
    }
    updateBillingNotificationBadges(billingNotificationState);
    if (result.ok) {
      transactions = [];
      offset = 0;
      await loadMore();
      await markBillingNotificationsAsRead();
      scheduleBillingNotificationRefresh();
      const backendData = result.data || null;
      const backendMessage =
        (backendData && typeof backendData.message === 'string'
          ? backendData.message
          : typeof backendData === 'string'
          ? backendData
          : '') || 'Sincronización completada';
      const backendCounts = extractEventCountsFromPayload(backendData);
      if (typeof showAlertModal === 'function') {
        const summaryLines = backendCounts
          ? getBillingEventSummaryLines(backendCounts)
          : initialSummaryLines;
        const summaryHtml = summaryLines
          .map(line => `<div>${escapeHtml(line)}</div>`)
          .join('');
        const escapedMessage = escapeHtml(backendMessage).replace(/\n/g, '<br>');
        const messageHtmlParts = [];
        if (backendMessage) {
          messageHtmlParts.push(`<p class="mb-2">${escapedMessage}</p>`);
        }
        if (summaryHtml) {
          messageHtmlParts.push(`<div>${summaryHtml}</div>`);
        }
        const messageHtml = messageHtmlParts.join('');
        if (messageHtml) {
          showAlertModal(backendMessage, {
            title: 'Sincronización completada',
            html: messageHtml
          });
        }
      }
    } else {
      scheduleBillingNotificationRefresh();
      if (result.error) {
        showAlertModal(result.error, {
          title: 'Error',
          confirmClass: 'btn-danger'
        });
      }
    }
  });
}
