import {
  fetchAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  fetchFrequents,
  createFrequent,
  updateFrequent,
  deleteFrequent
} from './api.js?v=1';
import {
  renderAccount,
  renderFrequent,
  showOverlay,
  hideOverlay,
} from './ui.js?v=1';
import { CURRENCIES } from './constants.js';

const tbody = document.querySelector('#account-table tbody');
const modalEl = document.getElementById('accountModal');
const accModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('account-form');
const addBtn = document.getElementById('add-account');
const alertBox = document.getElementById('acc-alert');
const currencySelect = form.currency;
const idField = form.querySelector('input[name="id"]');
const colorInput = form.querySelector('input[name="color"]');
const colorBtn = document.getElementById('color-btn');
const modalTitle = modalEl.querySelector('.modal-title');
let accounts = [];
const confirmEl = document.getElementById('confirmModal');
const confirmModal = new bootstrap.Modal(confirmEl);
const confirmMessage = confirmEl.querySelector('#confirm-message');
const confirmBtn = confirmEl.querySelector('#confirm-yes');
let accountToDelete = null;

const freqTbody = document.querySelector('#freq-table tbody');
const freqModalEl = document.getElementById('freqModal');
const freqModal = new bootstrap.Modal(freqModalEl);
const freqForm = document.getElementById('freq-form');
const addFreqBtn = document.getElementById('add-freq');
const freqAlertBox = document.getElementById('freq-alert');
const freqIdField = freqForm.querySelector('input[name="id"]');
const freqModalTitle = freqModalEl.querySelector('.modal-title');
const freqConfirmEl = document.getElementById('confirmFreqModal');
const freqConfirmModal = new bootstrap.Modal(freqConfirmEl);
const freqConfirmMessage = freqConfirmEl.querySelector('#confirm-freq-message');
const freqConfirmBtn = freqConfirmEl.querySelector('#confirm-freq-yes');
let freqToDelete = null;
let frequents = [];

function populateCurrencies() {
  currencySelect.innerHTML = '';
  CURRENCIES.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    currencySelect.appendChild(opt);
  });
}

addBtn.addEventListener('click', async () => {
  form.reset();
  populateCurrencies();
  idField.value = '';
  alertBox.classList.add('d-none');
  colorInput.value = '#000000';
  colorBtn.style.color = '#000000';
  form.is_billing.checked = false;
  modalTitle.textContent = 'Nueva cuenta';
  accModal.show();
});

  colorBtn.addEventListener('click', () => {
    const rect = colorBtn.getBoundingClientRect();
    colorInput.style.left = `${rect.left}px`;
    colorInput.style.top = `${rect.bottom}px`;
    colorInput.click();
  });

colorInput.addEventListener('input', e => {
  colorBtn.style.color = e.target.value;
});

form.addEventListener('submit', async e => {
  e.preventDefault();
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  const payload = {
    name: data.get('name'),
    currency: data.get('currency'),
    opening_balance: parseFloat(data.get('opening_balance') || '0'),
    is_active: true,
    color: data.get('color') || '#000000',
    is_billing: form.is_billing.checked
  };
  let replaceBilling = false;
  if (payload.is_billing) {
    const existing = accounts.find(a => a.is_billing && a.id !== parseInt(idField.value || '0', 10));
    if (existing) {
      const ok = confirm(`La cuenta "${existing.name}" ya es de facturación. ¿Reemplazarla?`);
      if (!ok) return;
      replaceBilling = true;
    }
  }
  showOverlay();
  let result;
  if (idField.value) {
    result = await updateAccount(idField.value, payload, replaceBilling);
  } else {
    result = await createAccount(payload, replaceBilling);
  }
  hideOverlay();
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    alertBox.classList.add('alert-success');
    alertBox.textContent = 'Cuenta guardada';
    if (result.account && !idField.value) {
      idField.value = result.account.id;
    }
    tbody.innerHTML = '';
    await loadAccounts();
    accModal.hide();
  } else {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = result.error || 'Error al guardar';
  }
});

async function loadAccounts() {
  accounts = await fetchAccounts();
  accounts.forEach(acc => {
    renderAccount(tbody, acc, startEdit, removeAccount);
  });
}


async function startEdit(acc) {
  form.reset();
  populateCurrencies();
  form.name.value = acc.name;
  form.currency.value = acc.currency;
  form.opening_balance.value = acc.opening_balance;
  idField.value = acc.id;
  const color = acc.color || '#000000';
  colorInput.value = color;
  colorBtn.style.color = color;
  form.is_billing.checked = acc.is_billing;
  alertBox.classList.add('d-none');
  modalTitle.textContent = 'Editar cuenta';
  accModal.show();
}

async function removeAccount(acc) {
  accountToDelete = acc;
  confirmMessage.textContent = `¿Eliminar cuenta "${acc.name}"?`;
  confirmModal.show();
}

confirmBtn.addEventListener('click', async () => {
  if (!accountToDelete) return;
  confirmModal.hide();
  showOverlay();
  const result = await deleteAccount(accountToDelete.id);
  hideOverlay();
  if (result.ok) {
    tbody.innerHTML = '';
    await loadAccounts();
  } else {
    alert(result.error || 'Error al eliminar');
  }
  accountToDelete = null;
});

addFreqBtn.addEventListener('click', () => {
  freqForm.reset();
  freqIdField.value = '';
  freqAlertBox.classList.add('d-none');
  freqModalTitle.textContent = 'Nueva transacción frecuente';
  freqModal.show();
});

freqForm.addEventListener('submit', async e => {
  e.preventDefault();
  if (!freqForm.reportValidity()) return;
  const data = new FormData(freqForm);
  const payload = {
    description: data.get('description')
  };
  showOverlay();
  let result;
  if (freqIdField.value) {
    result = await updateFrequent(freqIdField.value, payload);
  } else {
    result = await createFrequent(payload);
  }
  hideOverlay();
  freqAlertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    freqAlertBox.classList.add('alert-success');
    freqAlertBox.textContent = 'Frecuente guardado';
    freqTbody.innerHTML = '';
    await loadFrequents();
  } else {
    freqAlertBox.classList.add('alert-danger');
    freqAlertBox.textContent = result.error || 'Error al guardar';
  }
});

async function loadFrequents() {
  frequents = await fetchFrequents();
  freqTbody.innerHTML = '';
  frequents.forEach(freq => {
    renderFrequent(freqTbody, freq, startEditFreq, removeFreq);
  });
}

function startEditFreq(freq) {
  freqForm.reset();
  freqForm.description.value = freq.description;
  freqIdField.value = freq.id;
  freqAlertBox.classList.add('d-none');
  freqModalTitle.textContent = 'Editar transacción frecuente';
  freqModal.show();
}

async function removeFreq(freq) {
  freqToDelete = freq;
  freqConfirmMessage.textContent = `¿Eliminar transacción frecuente "${freq.description}"?`;
  freqConfirmModal.show();
}

freqConfirmBtn.addEventListener('click', async () => {
  if (!freqToDelete) return;
  freqConfirmModal.hide();
  showOverlay();
  const result = await deleteFrequent(freqToDelete.id);
  hideOverlay();
  if (result.ok) {
    freqTbody.innerHTML = '';
    await loadFrequents();
  } else {
    alert(result.error || 'Error al eliminar');
  }
  freqToDelete = null;
});
loadAccounts().then(() => loadFrequents());
