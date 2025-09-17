import { fetchAccounts, fetchInvoices, createInvoice } from './api.js?v=1';
import { renderInvoice, showOverlay, hideOverlay } from './ui.js?v=1';
import { sanitizeDecimalInput, parseDecimal, formatCurrency } from './money.js?v=1';

const tbody = document.querySelector('#inv-table tbody');
const container = document.getElementById('table-container');
const modalEl = document.getElementById('invModal');
const invModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('inv-form');
const alertBox = document.getElementById('inv-alert');
const searchBox = document.getElementById('search-box');
const headers = document.querySelectorAll('#inv-table thead th.sortable');
const amountInput = form.amount;
const ivaPercentInput = form.iva_percent;
const ivaAmountInput = form.iva_amount;
const iibbPercentInput = form.iibb_percent;
const iibbAmountInput = form.iibb_amount;
const iibbRow = document.getElementById('iibb-row');
const retRow = document.getElementById('ret-row');
const retencionesInput = form.retenciones;
const billingAccountLabel = document.getElementById('billing-account');
const defaultIvaPercent = ivaPercentInput.value || '21';
const defaultIibbPercent = iibbPercentInput.value || '3';

function formatTaxAmount(value) {
  const amount = Number.isFinite(value) ? value : 0;
  return formatCurrency(amount);
}

function isManualPercent(input) {
  return input?.dataset.manual === 'true';
}

function showManualPlaceholder(input) {
  if (!input) return;
  input.placeholder = 'MOD';
  input.classList.add('manual-value');
}

function hideManualPlaceholder(input) {
  if (!input) return;
  input.placeholder = '';
  input.classList.remove('manual-value');
}

function setManualPercent(percentInput, amountInput, percentValue) {
  percentInput.dataset.manual = 'true';
  percentInput.dataset.manualPercent = String(percentValue ?? 0);
  percentInput.value = '';
  showManualPlaceholder(percentInput);
  amountInput.dataset.manual = 'true';
}

function clearManualPercent(percentInput, amountInput, fallbackPercent = null) {
  let manualStored = null;
  const wasManual = isManualPercent(percentInput);
  if (wasManual) {
    manualStored = percentInput.dataset.manualPercent ?? null;
    delete percentInput.dataset.manual;
    delete percentInput.dataset.manualPercent;
  }
  if (amountInput.dataset.manual === 'true') {
    delete amountInput.dataset.manual;
  }
  if (wasManual) {
    hideManualPlaceholder(percentInput);
    const nextValue = fallbackPercent ?? manualStored;
    percentInput.value =
      nextValue !== null && nextValue !== undefined && nextValue !== ''
        ? String(nextValue)
        : '';
  }
}

function getPercentValue(percentInput) {
  if (isManualPercent(percentInput)) {
    return parseDecimal(percentInput.dataset.manualPercent);
  }
  return parseDecimal(percentInput.value);
}

function getAmountValue(amountInput) {
  return Math.abs(parseDecimal(amountInput.value));
}

function roundToTwo(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  return Math.round((num + Number.EPSILON) * 100) / 100;
}
let offset = 0;
const limit = 50;
let loading = false;
let accounts = [];
let accountMap = {};
let billingAccount = null;
let invoices = [];
let sortColumn = 1;
let sortAsc = false;

function renderInvoices() {
  const q = searchBox.value.trim().toLowerCase();
  const filtered = invoices.filter(inv => {
    const typeText = inv.type === 'sale' ? 'venta' : 'compra';
    return (
      inv.description.toLowerCase().includes(q) ||
      (inv.number || '').toLowerCase().includes(q) ||
      typeText.includes(q)
    );
  });
  filtered.sort((a, b) => {
    switch (sortColumn) {
      case 0:
        return sortAsc
          ? (a.number || '').localeCompare(b.number || '')
          : (b.number || '').localeCompare(a.number || '');
      case 1:
        return sortAsc
          ? new Date(a.date) - new Date(b.date)
          : new Date(b.date) - new Date(a.date);
      case 2:
        return sortAsc
          ? a.type.localeCompare(b.type)
          : b.type.localeCompare(a.type);
      case 3:
        return sortAsc
          ? a.description.localeCompare(b.description)
          : b.description.localeCompare(a.description);
      case 4:
        // Comparar por monto total (importe sin impuestos + IVA)
        const totalWithIvaA = Math.abs(
          Number(a.amount) + Number(a.iva_amount) + Number(a.retenciones || 0)
        );
        const totalWithIvaB = Math.abs(
          Number(b.amount) + Number(b.iva_amount) + Number(b.retenciones || 0)
        );
        return sortAsc
          ? totalWithIvaA - totalWithIvaB
          : totalWithIvaB - totalWithIvaA;
      default:
        return 0;
    }
  });
  tbody.innerHTML = '';
  filtered.forEach(inv => renderInvoice(tbody, inv, accountMap));
}

function recalcTaxes() {
  const baseAmount = Math.abs(parseDecimal(amountInput.value));
  const ivaManual = isManualPercent(ivaPercentInput);
  let ivaAmountValue = getAmountValue(ivaAmountInput);
  if (!ivaManual) {
    const ivaPercent = parseDecimal(ivaPercentInput.value);
    ivaAmountValue = (baseAmount * ivaPercent) / 100;
    ivaAmountInput.value = formatTaxAmount(ivaAmountValue);
  } else {
    const percent = baseAmount ? (ivaAmountValue / baseAmount) * 100 : 0;
    ivaPercentInput.dataset.manualPercent = String(percent);
  }

  if (iibbPercentInput.disabled) {
    iibbAmountInput.value = formatTaxAmount(0);
    clearManualPercent(iibbPercentInput, iibbAmountInput);
    return;
  }

  const iibbManual = isManualPercent(iibbPercentInput);
  let iibbAmountValue = getAmountValue(iibbAmountInput);
  const iibbBase = baseAmount + ivaAmountValue;
  if (!iibbManual) {
    const iibbPercent = parseDecimal(iibbPercentInput.value);
    iibbAmountValue = (iibbBase * iibbPercent) / 100;
    iibbAmountInput.value = formatTaxAmount(iibbAmountValue);
  } else {
    const percent = iibbBase ? (iibbAmountValue / iibbBase) * 100 : 0;
    iibbPercentInput.dataset.manualPercent = String(percent);
  }
}

amountInput.addEventListener('input', () => {
  sanitizeDecimalInput(amountInput);
  recalcTaxes();
});

amountInput.addEventListener('blur', () => {
  if (!amountInput.value.trim()) return;
  const value = Math.abs(parseDecimal(amountInput.value));
  amountInput.value = formatTaxAmount(value);
});

ivaPercentInput.addEventListener('focus', () => {
  if (!isManualPercent(ivaPercentInput)) return;
  hideManualPlaceholder(ivaPercentInput);
  const percent = parseDecimal(ivaPercentInput.dataset.manualPercent);
  ivaPercentInput.value = percent ? percent.toFixed(2) : '0.00';
  ivaPercentInput.select();
});

ivaPercentInput.addEventListener('blur', () => {
  if (isManualPercent(ivaPercentInput)) {
    ivaPercentInput.value = '';
    showManualPlaceholder(ivaPercentInput);
  }
});

ivaPercentInput.addEventListener('input', () => {
  sanitizeDecimalInput(ivaPercentInput);
  if (isManualPercent(ivaPercentInput)) {
    clearManualPercent(ivaPercentInput, ivaAmountInput);
  }
  recalcTaxes();
});

ivaAmountInput.addEventListener('input', () => {
  sanitizeDecimalInput(ivaAmountInput);
  if (!ivaAmountInput.value.trim()) {
    clearManualPercent(ivaPercentInput, ivaAmountInput);
    recalcTaxes();
    return;
  }
  const baseAmount = Math.abs(parseDecimal(amountInput.value));
  const ivaAmountValue = getAmountValue(ivaAmountInput);
  const percent = baseAmount ? (ivaAmountValue / baseAmount) * 100 : 0;
  setManualPercent(ivaPercentInput, ivaAmountInput, percent);
  recalcTaxes();
});

ivaAmountInput.addEventListener('blur', () => {
  if (!ivaAmountInput.value.trim()) return;
  const value = getAmountValue(ivaAmountInput);
  ivaAmountInput.value = formatTaxAmount(value);
});

iibbPercentInput.addEventListener('focus', () => {
  if (iibbPercentInput.disabled || !isManualPercent(iibbPercentInput)) return;
  hideManualPlaceholder(iibbPercentInput);
  const percent = parseDecimal(iibbPercentInput.dataset.manualPercent);
  iibbPercentInput.value = percent ? percent.toFixed(2) : '0.00';
  iibbPercentInput.select();
});

iibbPercentInput.addEventListener('blur', () => {
  if (iibbPercentInput.disabled) return;
  if (isManualPercent(iibbPercentInput)) {
    iibbPercentInput.value = '';
    showManualPlaceholder(iibbPercentInput);
  }
});

iibbPercentInput.addEventListener('input', () => {
  if (iibbPercentInput.disabled) return;
  sanitizeDecimalInput(iibbPercentInput);
  if (isManualPercent(iibbPercentInput)) {
    clearManualPercent(iibbPercentInput, iibbAmountInput);
  }
  recalcTaxes();
});

iibbAmountInput.addEventListener('input', () => {
  if (iibbAmountInput.disabled) return;
  sanitizeDecimalInput(iibbAmountInput);
  if (!iibbAmountInput.value.trim()) {
    clearManualPercent(iibbPercentInput, iibbAmountInput);
    recalcTaxes();
    return;
  }
  const baseAmount = Math.abs(parseDecimal(amountInput.value));
  const ivaAmountValue = getAmountValue(ivaAmountInput);
  const iibbAmountValue = getAmountValue(iibbAmountInput);
  const iibbBase = baseAmount + ivaAmountValue;
  const percent = iibbBase ? (iibbAmountValue / iibbBase) * 100 : 0;
  setManualPercent(iibbPercentInput, iibbAmountInput, percent);
  recalcTaxes();
});

iibbAmountInput.addEventListener('blur', () => {
  if (iibbAmountInput.disabled || !iibbAmountInput.value.trim()) return;
  const value = getAmountValue(iibbAmountInput);
  iibbAmountInput.value = formatTaxAmount(value);
});

retencionesInput.addEventListener('input', () => {
  if (retencionesInput.disabled) return;
  sanitizeDecimalInput(retencionesInput);
});

retencionesInput.addEventListener('blur', () => {
  if (retencionesInput.disabled || !retencionesInput.value.trim()) return;
  const value = getAmountValue(retencionesInput);
  retencionesInput.value = formatTaxAmount(value);
});

async function loadMore() {
  if (loading) return;
  loading = true;
  const data = await fetchInvoices(limit, offset);
  invoices = invoices.concat(data);
  offset += data.length;
  renderInvoices();
  loading = false;
}

function openModal(type) {
  if (!billingAccount) {
    alert('Se requiere una cuenta de facturación');
    return;
  }
  form.reset();
  amountInput.value = '';
  document.getElementById('form-title').textContent =
    type === 'sale' ? 'Nueva Factura de Venta' : 'Nueva Factura de Compra';
  form.account_id.value = billingAccount.id;
  billingAccountLabel.textContent = billingAccount.name;
  billingAccountLabel.style.color = billingAccount.color;
  form.dataset.type = type;
  clearManualPercent(ivaPercentInput, ivaAmountInput);
  clearManualPercent(iibbPercentInput, iibbAmountInput);
  ivaPercentInput.value = defaultIvaPercent;
  ivaAmountInput.value = formatTaxAmount(0);
  alertBox.classList.add('d-none');
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  form.date.value = today;
  const isPurchase = type === 'purchase';
  if (retRow) {
    retRow.classList.toggle('d-none', !isPurchase);
  }
  retencionesInput.disabled = !isPurchase;
  retencionesInput.value = formatTaxAmount(0);
  iibbRow.classList.toggle('d-none', isPurchase);
  iibbPercentInput.disabled = isPurchase;
  iibbAmountInput.disabled = isPurchase;
  iibbPercentInput.value = isPurchase ? '0' : defaultIibbPercent;
  iibbAmountInput.value = formatTaxAmount(0);
  if (!isPurchase) {
    retencionesInput.value = formatTaxAmount(0);
  }
  recalcTaxes();
  invModal.show();
}

document.getElementById('add-sale').addEventListener('click', () => openModal('sale'));
document.getElementById('add-purchase').addEventListener('click', () => openModal('purchase'));
searchBox.addEventListener('input', renderInvoices);

headers.forEach((th, index) => {
  th.addEventListener('click', () => {
    if (sortColumn === index) {
      sortAsc = !sortAsc;
    } else {
      sortColumn = index;
      sortAsc = true;
    }
    updateSortIcons();
    renderInvoices();
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
    const isPurchase = form.dataset.type === 'purchase';
    const amount = Math.abs(parseDecimal(data.get('amount'))) || 0;
    const ivaPercent = roundToTwo(Math.abs(getPercentValue(ivaPercentInput)));
    const ivaAmount = roundToTwo(getAmountValue(ivaAmountInput));
    const iibbPercentValue = isPurchase ? 0 : roundToTwo(Math.abs(getPercentValue(iibbPercentInput)));
    const iibbAmount = roundToTwo(getAmountValue(iibbAmountInput));
    const retencionesAmount = isPurchase ? roundToTwo(getAmountValue(retencionesInput)) : 0;
    const payload = {
      date: data.get('date'),
      number: data.get('number'),
      description: data.get('description'),
      amount,
      account_id: billingAccount.id,
      type: form.dataset.type,
      iva_percent: ivaPercent,
      iibb_percent: isPurchase ? 0 : iibbPercentValue,
      retenciones: retencionesAmount
    };
    if (isManualPercent(ivaPercentInput)) {
      payload.iva_amount = ivaAmount;
    }
    if (isPurchase) {
      payload.iibb_amount = 0;
    } else if (isManualPercent(iibbPercentInput)) {
      payload.iibb_amount = iibbAmount;
    }
    const today = new Date().toISOString().split('T')[0];
    if (payload.date > today) {
      alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
      alertBox.classList.add('alert-danger');
      alertBox.textContent = 'La fecha no puede ser futura';
      return;
    }

  showOverlay();
  const result = await createInvoice(payload);
  hideOverlay();
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    alertBox.classList.add('alert-success');
    alertBox.textContent = 'Factura guardada';
    invoices = [];
    offset = 0;
    await loadMore();
    setTimeout(() => {
      invModal.hide();
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
  billingAccount = accounts.find(a => a.is_billing);
  await loadMore();
  updateSortIcons();
})();
