import {
  fetchAccounts,
  fetchTransactions,
  createTransaction,
  fetchFrequents,
  updateTransaction,
  deleteTransaction,
  syncBillingTransactions
} from './api.js?v=2';
import {
  renderTransaction,
  populateAccounts,
  showOverlay,
  hideOverlay,
} from './ui.js?v=2';
import { sanitizeDecimalInput, parseDecimal, formatCurrency } from './money.js?v=1';

const tbody = document.querySelector('#tx-table tbody');
const container = document.getElementById('table-container');
const modalEl = document.getElementById('txModal');
const txModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('tx-form');
const alertBox = document.getElementById('tx-alert');
const searchBox = document.getElementById('search-box');
const headers = document.querySelectorAll('#tx-table thead th.sortable');
const freqCheck = document.getElementById('freq-check');
const freqSelect = document.getElementById('freq-select');
const descInput = document.getElementById('desc-input');
const amountInput = form.amount;
const billingSyncButton = document.getElementById('billing-sync-button');

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

function renderTransactions() {
  const q = searchBox.value.trim().toLowerCase();
  const filtered = transactions.filter(tx => {
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
  frequents = await fetchFrequents();
  frequentMap = Object.fromEntries(frequents.map(f => [f.id, f]));
  await loadMore();
  updateSortIcons();
})();

if (billingSyncButton) {
  const originalLabel = billingSyncButton.textContent;
  billingSyncButton.addEventListener('click', async () => {
    if (billingSyncButton.disabled) return;
    billingSyncButton.disabled = true;
    const spinnerColor = billingSyncButton.style.color || '#0d6efd';
    billingSyncButton.innerHTML =
      `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true" style="color:${spinnerColor}"></span>` +
      'Sincronizando...';
    showOverlay();
    const result = await syncBillingTransactions();
    hideOverlay();
    billingSyncButton.disabled = false;
    billingSyncButton.textContent = originalLabel;
    if (result.ok) {
      transactions = [];
      offset = 0;
      await loadMore();
      if (result.data?.message) {
        showAlertModal(result.data.message, {
          title: 'Sincronización completada'
        });
      }
    } else if (result.error) {
      showAlertModal(result.error, {
        title: 'Error',
        confirmClass: 'btn-danger'
      });
    }
  });
}
