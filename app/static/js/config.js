import {
  fetchAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  fetchTaxes,
  createTax,
  updateTax,
  deleteTax,
  fetchAccountTaxes,
  setAccountTaxes,
  fetchFrequents,
  createFrequent,
  updateFrequent,
  deleteFrequent
} from './api.js';
import {
  renderAccount,
  renderTax,
  renderFrequent,
  showOverlay,
  hideOverlay
} from './ui.js';
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
let accountMap = {};
const confirmEl = document.getElementById('confirmModal');
const confirmModal = new bootstrap.Modal(confirmEl);
const confirmMessage = confirmEl.querySelector('#confirm-message');
const confirmBtn = confirmEl.querySelector('#confirm-yes');
let accountToDelete = null;
const taxAssocList = document.getElementById('tax-assoc-list');
const assocBtn = document.getElementById('assoc-tax-btn');

const taxTbody = document.querySelector('#tax-table tbody');
const taxModalEl = document.getElementById('taxModal');
const taxModal = new bootstrap.Modal(taxModalEl);
const taxForm = document.getElementById('tax-form');
const addTaxBtn = document.getElementById('add-tax');
const taxAlertBox = document.getElementById('tax-alert');
const taxIdField = taxForm.querySelector('input[name="id"]');
const taxModalTitle = taxModalEl.querySelector('.modal-title');
let taxes = [];
const taxConfirmEl = document.getElementById('confirmTaxModal');
const taxConfirmModal = new bootstrap.Modal(taxConfirmEl);
const taxConfirmMessage = taxConfirmEl.querySelector('#confirm-tax-message');
const taxConfirmBtn = taxConfirmEl.querySelector('#confirm-tax-yes');
let taxToDelete = null;

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

function populateTaxOptions(selected = []) {
  taxAssocList.innerHTML = '';
  taxes.forEach(t => {
    const div = document.createElement('div');
    div.className = 'form-check';
    const input = document.createElement('input');
    input.className = 'form-check-input';
    input.type = 'checkbox';
    input.id = `tax-${t.id}`;
    input.value = t.id;
    if (selected.includes(t.id)) input.checked = true;
    const label = document.createElement('label');
    label.className = 'form-check-label';
    label.setAttribute('for', input.id);
    label.textContent = t.name;
    div.appendChild(input);
    div.appendChild(label);
    taxAssocList.appendChild(div);
  });
}

  addBtn.addEventListener('click', async () => {
    form.reset();
    populateCurrencies();
    idField.value = '';
    alertBox.classList.add('d-none');
    colorInput.value = '#000000';
    colorBtn.style.color = '#000000';
    modalTitle.textContent = 'Nueva cuenta';
    if (taxes.length === 0) {
      taxes = await fetchTaxes();
    }
    populateTaxOptions();
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
    color: data.get('color') || '#000000'
  };
  showOverlay();
  let result;
  if (idField.value) {
    result = await updateAccount(idField.value, payload);
  } else {
    result = await createAccount(payload);
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
  const taxesList = await Promise.all(accounts.map(acc => fetchAccountTaxes(acc.id)));
  accounts.forEach((acc, idx) => {
    acc.taxes = taxesList[idx];
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
  alertBox.classList.add('d-none');
  modalTitle.textContent = 'Editar cuenta';
  if (taxes.length === 0) {
    taxes = await fetchTaxes();
  }
  const accountTaxes = acc.taxes || await fetchAccountTaxes(acc.id);
  const selected = accountTaxes.map(t => t.id);
  populateTaxOptions(selected);
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

addTaxBtn.addEventListener('click', () => {
  taxForm.reset();
  taxIdField.value = '';
  taxAlertBox.classList.add('d-none');
  taxModalTitle.textContent = 'Nuevo impuesto';
  taxModal.show();
});

taxForm.addEventListener('submit', async e => {
  e.preventDefault();
  if (!taxForm.reportValidity()) return;
  const data = new FormData(taxForm);
  const payload = {
    name: data.get('name'),
    rate: parseFloat(data.get('rate') || '0')
  };
  showOverlay();
  let result;
  if (taxIdField.value) {
    result = await updateTax(taxIdField.value, payload);
  } else {
    result = await createTax(payload);
  }
  hideOverlay();
  taxAlertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    taxAlertBox.classList.add('alert-success');
    taxAlertBox.textContent = 'Impuesto guardado';
    taxTbody.innerHTML = '';
    await loadTaxes();
  } else {
    taxAlertBox.classList.add('alert-danger');
    taxAlertBox.textContent = result.error || 'Error al guardar';
  }
});

async function loadTaxes() {
  taxes = await fetchTaxes();
  taxes.forEach(t => renderTax(taxTbody, t, startEditTax, removeTax));
}

function startEditTax(tax) {
  taxForm.reset();
  taxForm.name.value = tax.name;
  taxForm.rate.value = tax.rate;
  taxIdField.value = tax.id;
  taxAlertBox.classList.add('d-none');
  taxModalTitle.textContent = 'Editar impuesto';
  taxModal.show();
}

async function removeTax(tax) {
  taxToDelete = tax;
  taxConfirmMessage.textContent = `¿Eliminar impuesto "${tax.name}"?`;
  taxConfirmModal.show();
}

taxConfirmBtn.addEventListener('click', async () => {
  if (!taxToDelete) return;
  taxConfirmModal.hide();
  showOverlay();
  const result = await deleteTax(taxToDelete.id);
  hideOverlay();
  if (result.ok) {
    taxTbody.innerHTML = '';
    await loadTaxes();
  } else {
    alert(result.error || 'Error al eliminar');
  }
  taxToDelete = null;
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

assocBtn.addEventListener('click', async () => {
  if (!idField.value) {
    alertBox.classList.remove('d-none', 'alert-success');
    alertBox.classList.add('alert-danger');
    alertBox.textContent = 'Guarde la cuenta antes de asociar impuestos';
    return;
  }
  const selected = Array.from(
    taxAssocList.querySelectorAll('input[type="checkbox"]:checked')
  ).map(i => Number(i.value));
  showOverlay();
  const result = await setAccountTaxes(idField.value, selected);
  hideOverlay();
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    alertBox.classList.add('alert-success');
    alertBox.textContent = 'Impuestos asociados';
    tbody.innerHTML = '';
    await loadAccounts();
  } else {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = result.error || 'Error al guardar';
  }
});

loadAccounts().then(() => loadFrequents());
loadTaxes();
