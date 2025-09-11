import { fetchAccounts, fetchInvoices, createInvoice } from './api.js?v=1';
import {
  renderInvoice,
  showOverlay,
  hideOverlay,
  formatCurrency,
} from './ui.js?v=1';

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
const billingAccountLabel = document.getElementById('billing-account');
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
        const totalWithIvaA = Math.abs(Number(a.amount) + Number(a.iva_amount));
        const totalWithIvaB = Math.abs(Number(b.amount) + Number(b.iva_amount));
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
  const amount = parseFloat(amountInput.value) || 0;
  const ivaPercent = parseFloat(ivaPercentInput.value) || 0;
  const ivaAmount = (amount * ivaPercent) / 100;
  ivaAmountInput.value = formatCurrency(ivaAmount);
  const iibbPercent = parseFloat(iibbPercentInput.value) || 0;
  const iibbAmount = ((amount + ivaAmount) * iibbPercent) / 100;
  iibbAmountInput.value = formatCurrency(iibbAmount);
}
amountInput.addEventListener('input', recalcTaxes);
ivaPercentInput.addEventListener('input', recalcTaxes);
iibbPercentInput.addEventListener('input', recalcTaxes);

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
  document.getElementById('form-title').textContent =
    type === 'sale' ? 'Nueva Factura de Venta' : 'Nueva Factura de Compra';
  form.account_id.value = billingAccount.id;
  billingAccountLabel.textContent = billingAccount.name;
  billingAccountLabel.style.color = billingAccount.color;
  form.dataset.type = type;
  alertBox.classList.add('d-none');
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  form.date.value = today;
  const isPurchase = type === 'purchase';
  iibbRow.classList.toggle('d-none', isPurchase);
  iibbPercentInput.disabled = isPurchase;
  iibbAmountInput.disabled = isPurchase;
  iibbPercentInput.value = isPurchase ? 0 : 3;
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
    const amount = Math.abs(parseFloat(data.get('amount')));
    const payload = {
      date: data.get('date'),
      number: data.get('number'),
      description: data.get('description'),
      amount,
    account_id: billingAccount.id,
    type: form.dataset.type,
    iva_percent: parseFloat(data.get('iva_percent')) || 0,
    iibb_percent: isPurchase ? 0 : parseFloat(data.get('iibb_percent')) || 0
  };
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
