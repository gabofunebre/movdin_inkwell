import {
  fetchAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  fetchFrequents,
  createFrequent,
  updateFrequent,
  deleteFrequent
} from './api.js';
import {
  renderAccount,
  renderFrequent,
  showOverlay,
  hideOverlay
} from './ui.js';
import { CURRENCIES } from './constants.js';
document.addEventListener('DOMContentLoaded', () => {
  const tbody = document.querySelector('#account-table tbody');
  const modalEl = document.getElementById('accountModal');
  const accModal = window.bootstrap && modalEl ? new bootstrap.Modal(modalEl) : null;
  const form = document.getElementById('account-form');
  const addBtn = document.getElementById('add-account');
  const alertBox = document.getElementById('acc-alert');
  const currencySelect = form?.currency;
  const idField = form?.querySelector('input[name="id"]');
  const colorInput = form?.querySelector('input[name="color"]');
  const colorBtn = document.getElementById('color-btn');
  const modalTitle = modalEl?.querySelector('.modal-title');
  let accounts = [];
  const confirmEl = document.getElementById('confirmModal');
  const confirmModal = window.bootstrap && confirmEl ? new bootstrap.Modal(confirmEl) : null;
  const confirmMessage = confirmEl?.querySelector('#confirm-message');
  const confirmBtn = confirmEl?.querySelector('#confirm-yes');
  let accountToDelete = null;

  const freqTbody = document.querySelector('#freq-table tbody');
  const freqModalEl = document.getElementById('freqModal');
  const freqModal = window.bootstrap && freqModalEl ? new bootstrap.Modal(freqModalEl) : null;
  const freqForm = document.getElementById('freq-form');
  const addFreqBtn = document.getElementById('add-freq');
  const freqAlertBox = document.getElementById('freq-alert');
  const freqIdField = freqForm?.querySelector('input[name="id"]');
  const freqModalTitle = freqModalEl?.querySelector('.modal-title');
  const freqConfirmEl = document.getElementById('confirmFreqModal');
  const freqConfirmModal = window.bootstrap && freqConfirmEl ? new bootstrap.Modal(freqConfirmEl) : null;
  const freqConfirmMessage = freqConfirmEl?.querySelector('#confirm-freq-message');
  const freqConfirmBtn = freqConfirmEl?.querySelector('#confirm-freq-yes');
  let freqToDelete = null;
  let frequents = [];

  function populateCurrencies() {
    if (!currencySelect) return;
    currencySelect.innerHTML = '';
    CURRENCIES.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c;
      opt.textContent = c;
      currencySelect.appendChild(opt);
    });
  }

  if (addBtn && accModal) {
    addBtn.addEventListener('click', async () => {
      form?.reset();
      populateCurrencies();
      if (idField) idField.value = '';
      alertBox?.classList.add('d-none');
      if (colorInput) colorInput.value = '#000000';
      if (colorBtn) colorBtn.style.color = '#000000';
      if (modalTitle) modalTitle.textContent = 'Nueva cuenta';
      accModal.show();
    });
  }

  colorBtn?.addEventListener('click', () => {
    const rect = colorBtn.getBoundingClientRect();
    if (colorInput) {
      colorInput.style.left = `${rect.left}px`;
      colorInput.style.top = `${rect.bottom}px`;
      colorInput.click();
    }
  });

  colorInput?.addEventListener('input', e => {
    if (colorBtn) colorBtn.style.color = e.target.value;
  });

  form?.addEventListener('submit', async e => {
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
    if (idField?.value) {
      result = await updateAccount(idField.value, payload);
    } else {
      result = await createAccount(payload);
    }
    hideOverlay();
    alertBox?.classList.remove('d-none', 'alert-success', 'alert-danger');
    if (result.ok) {
      alertBox?.classList.add('alert-success');
      if (alertBox) alertBox.textContent = 'Cuenta guardada';
      if (result.account && !idField?.value) {
        if (idField) idField.value = result.account.id;
      }
      if (tbody) tbody.innerHTML = '';
      await loadAccounts();
      accModal?.hide();
    } else {
      alertBox?.classList.add('alert-danger');
      if (alertBox) alertBox.textContent = result.error || 'Error al guardar';
    }

  });

  async function loadAccounts() {
    accounts = await fetchAccounts();
    if (!tbody) return;
    accounts.forEach(acc => {
      renderAccount(tbody, acc, startEdit, removeAccount);
    });
  }

  async function startEdit(acc) {
    if (!form || !accModal) return;
    form.reset();
    populateCurrencies();
    form.name.value = acc.name;
    form.currency.value = acc.currency;
    form.opening_balance.value = acc.opening_balance;
    if (idField) idField.value = acc.id;
    const color = acc.color || '#000000';
    if (colorInput) colorInput.value = color;
    if (colorBtn) colorBtn.style.color = color;
    alertBox?.classList.add('d-none');
    if (modalTitle) modalTitle.textContent = 'Editar cuenta';
    accModal.show();
  }

  async function removeAccount(acc) {
    if (!confirmModal || !confirmMessage) return;
    accountToDelete = acc;
    confirmMessage.textContent = `¿Eliminar cuenta "${acc.name}"?`;
    confirmModal.show();
  }

  confirmBtn?.addEventListener('click', async () => {
    if (!accountToDelete) return;
    confirmModal?.hide();
    showOverlay();
    const result = await deleteAccount(accountToDelete.id);
    hideOverlay();
    if (result.ok) {
      if (tbody) tbody.innerHTML = '';
      await loadAccounts();
    } else {
      alert(result.error || 'Error al eliminar');
    }
    accountToDelete = null;
  });

  if (addFreqBtn && freqModal) {
    addFreqBtn.addEventListener('click', () => {
      freqForm?.reset();
      if (freqIdField) freqIdField.value = '';
      freqAlertBox?.classList.add('d-none');
      if (freqModalTitle) freqModalTitle.textContent = 'Nueva transacción frecuente';
      freqModal.show();
    });
  }

  freqForm?.addEventListener('submit', async e => {
    e.preventDefault();
    if (!freqForm.reportValidity()) return;
    const data = new FormData(freqForm);
    const payload = {
      description: data.get('description')
    };
    showOverlay();
    let result;
    if (freqIdField?.value) {
      result = await updateFrequent(freqIdField.value, payload);
    } else {
      result = await createFrequent(payload);
    }
    hideOverlay();
    freqAlertBox?.classList.remove('d-none', 'alert-success', 'alert-danger');
    if (result.ok) {
      freqAlertBox?.classList.add('alert-success');
      if (freqAlertBox) freqAlertBox.textContent = 'Frecuente guardado';
      if (freqTbody) freqTbody.innerHTML = '';
      await loadFrequents();
      freqModal?.hide();
    } else {
      freqAlertBox?.classList.add('alert-danger');
      if (freqAlertBox) freqAlertBox.textContent = result.error || 'Error al guardar';
    }
  });

  async function loadFrequents() {
    frequents = await fetchFrequents();
    if (!freqTbody) return;
    freqTbody.innerHTML = '';
    frequents.forEach(freq => {
      renderFrequent(freqTbody, freq, startEditFreq, removeFreq);
    });
  }

  function startEditFreq(freq) {
    if (!freqForm || !freqModal) return;
    freqForm.reset();
    freqForm.description.value = freq.description;
    if (freqIdField) freqIdField.value = freq.id;
    freqAlertBox?.classList.add('d-none');
    if (freqModalTitle) freqModalTitle.textContent = 'Editar transacción frecuente';
    freqModal.show();
  }
  async function removeFreq(freq) {
    if (!freqConfirmModal || !freqConfirmMessage) return;
    freqToDelete = freq;
    freqConfirmMessage.textContent = `¿Eliminar transacción frecuente "${freq.description}"?`;
    freqConfirmModal.show();
  }

  freqConfirmBtn?.addEventListener('click', async () => {
    if (!freqToDelete) return;
    freqConfirmModal?.hide();
    showOverlay();
    const result = await deleteFrequent(freqToDelete.id);
    hideOverlay();
    if (result.ok) {
      if (freqTbody) freqTbody.innerHTML = '';
      await loadFrequents();
    } else {
      alert(result.error || 'Error al eliminar');
    }
    freqToDelete = null;
  });

  const loaders = [];
  if (tbody) loaders.push(loadAccounts());
  if (freqTbody) loaders.push(loadFrequents());
  Promise.all(loaders);
});

