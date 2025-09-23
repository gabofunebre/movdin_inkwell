import {
  fetchRetentionCertificates,
  createRetentionCertificate,
  updateRetentionCertificate,
  deleteRetentionCertificate
} from './api.js?v=1';
import { formatCurrency, showOverlay, hideOverlay } from './ui.js?v=1';
import { sanitizeDecimalInput, parseDecimal } from './money.js?v=1';
import { CURRENCY_SYMBOLS } from './constants.js';

const table = document.getElementById('cert-table');
const tbody = table.querySelector('tbody');
const addBtn = document.getElementById('add-certificate');
const searchBox = document.getElementById('search-box');
const modalEl = document.getElementById('certModal');
const certModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('cert-form');
const modalTitle = document.getElementById('cert-form-title');
const alertBox = document.getElementById('cert-alert');
const amountInput = form.amount;
const withheldTaxInput = form.elements['withheld_tax'] || form.concept;
const isAdmin = Boolean(window.isAdmin);
const columnCount = table.querySelectorAll('thead th').length;
const currencyCode = window.certCurrency || 'ARS';
const currencySymbol = CURRENCY_SYMBOLS[currencyCode] || '';

let certificates = [];
let activeActionRow = null;
let activeDataRow = null;

function normalizeCertificate(cert) {
  const withheldTax = cert.withheld_tax ?? cert.concept ?? '';
  return {
    ...cert,
    amount: Number(cert.amount),
    withheld_tax: withheldTax
  };
}

function formatDate(value) {
  const dateObj = new Date(value);
  if (Number.isNaN(dateObj.getTime())) return value;
  return dateObj
    .toLocaleDateString('es-ES', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    })
    .replace('.', '');
}

function clearActionRow() {
  if (activeActionRow && activeActionRow.parentElement) {
    activeActionRow.parentElement.removeChild(activeActionRow);
  }
  if (activeDataRow) {
    activeDataRow.classList.remove('cert-row-active');
  }
  activeActionRow = null;
  activeDataRow = null;
}

function createActionButton({
  label,
  icon,
  className,
  onClick
}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `btn btn-sm ${className} cert-action-btn`;
  button.innerHTML = `<i class="${icon} me-1"></i>${label}`;
  button.addEventListener('click', event => {
    event.stopPropagation();
    onClick();
  });
  return button;
}

function showActionRow(row, cert) {
  clearActionRow();
  activeDataRow = row;
  activeDataRow.classList.add('cert-row-active');

  const actionRow = document.createElement('tr');
  actionRow.className = 'cert-action-row';

  const actionCell = document.createElement('td');
  actionCell.colSpan = columnCount;

  const actionsWrapper = document.createElement('div');
  actionsWrapper.className = 'cert-action-buttons';

  const editBtn = createActionButton({
    label: 'Editar',
    icon: 'bi bi-pencil',
    className: 'btn-outline-secondary',
    onClick: () => openEditModal(cert)
  });

  const deleteBtn = createActionButton({
    label: 'Eliminar',
    icon: 'bi bi-x',
    className: 'btn-outline-danger',
    onClick: () => confirmDelete(cert)
  });

  actionsWrapper.append(editBtn, deleteBtn);
  actionCell.appendChild(actionsWrapper);
  actionRow.appendChild(actionCell);
  row.after(actionRow);
  activeActionRow = actionRow;
}

function toggleActionRow(row, cert) {
  if (!isAdmin) {
    return;
  }
  if (activeDataRow === row) {
    clearActionRow();
    return;
  }
  showActionRow(row, cert);
}

function renderCertificates() {
  const query = searchBox.value.trim().toLowerCase();
  const filtered = certificates.filter(cert => {
    const number = cert.number?.toLowerCase() || '';
    const invoiceRef = cert.invoice_reference?.toLowerCase() || '';
    const withheldTax = (cert.withheld_tax ?? cert.concept)?.toLowerCase() || '';
    return (
      number.includes(query) ||
      invoiceRef.includes(query) ||
      withheldTax.includes(query)
    );
  });
  filtered.sort((a, b) => {
    if (a.date === b.date) {
      return b.id - a.id;
    }
    return new Date(b.date) - new Date(a.date);
  });
  clearActionRow();
  tbody.innerHTML = '';
  filtered.forEach(cert => {
    const tr = document.createElement('tr');
    tr.dataset.id = cert.id;

    const numberTd = document.createElement('td');
    numberTd.className = 'text-center';
    numberTd.textContent = cert.number;

    const dateTd = document.createElement('td');
    dateTd.className = 'text-center';
    dateTd.textContent = formatDate(cert.date);

    const refTd = document.createElement('td');
    refTd.className = 'text-center';
    refTd.textContent = cert.invoice_reference;

    const taxTd = document.createElement('td');
    taxTd.textContent = cert.withheld_tax ?? cert.concept ?? '';

    const amountTd = document.createElement('td');
    amountTd.className = 'text-end';
    const amountValue = Number.isFinite(cert.amount) ? cert.amount : 0;
    amountTd.textContent = `${currencySymbol} ${formatCurrency(Math.abs(amountValue))}`;

    tr.append(numberTd, dateTd, refTd, taxTd, amountTd);
    if (isAdmin) {
      tr.classList.add('cert-row-actionable');
      tr.addEventListener('click', () => toggleActionRow(tr, cert));
    }

    tbody.appendChild(tr);
  });
}

function setDateLimits() {
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
}

function openCreateModal() {
  clearActionRow();
  form.reset();
  modalTitle.textContent = 'Nuevo certificado';
  form.dataset.mode = 'create';
  delete form.dataset.id;
  setDateLimits();
  form.date.value = form.date.max;
  amountInput.value = '';
  if (withheldTaxInput) {
    withheldTaxInput.value = '';
  }
  clearError();
  certModal.show();
}

function openEditModal(cert) {
  clearActionRow();
  form.reset();
  modalTitle.textContent = 'Editar certificado';
  form.dataset.mode = 'edit';
  form.dataset.id = cert.id;
  setDateLimits();
  form.date.value = cert.date;
  form.number.value = cert.number;
  form.invoice_reference.value = cert.invoice_reference;
  if (withheldTaxInput) {
    withheldTaxInput.value = cert.withheld_tax ?? cert.concept ?? '';
  }
  amountInput.value = formatCurrency(Math.abs(Number(cert.amount)));
  clearError();
  certModal.show();
}

async function loadCertificates() {
  showOverlay();
  try {
    const data = await fetchRetentionCertificates(200, 0);
    certificates = Array.isArray(data)
      ? data.map(normalizeCertificate)
      : [];
    renderCertificates();
  } finally {
    hideOverlay();
  }
}

function showError(message) {
  alertBox.textContent = message;
  alertBox.classList.remove('d-none');
  alertBox.classList.add('alert-danger');
}

function clearError() {
  alertBox.classList.add('d-none');
  alertBox.textContent = '';
  alertBox.classList.remove('alert-danger');
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  clearError();
  const mode = form.dataset.mode || 'create';
  const payload = {
    date: form.date.value,
    number: form.number.value.trim(),
    invoice_reference: form.invoice_reference.value.trim(),
    concept: withheldTaxInput ? withheldTaxInput.value.trim() : ''
  };

  const amountValue = parseDecimal(amountInput.value);
  if (!Number.isFinite(amountValue) || amountValue <= 0) {
    showError('Ingrese un monto válido');
    return;
  }
  payload.amount = Math.abs(amountValue).toFixed(2);

  if (
    !payload.number ||
    !payload.invoice_reference ||
    !payload.concept ||
    !payload.date
  ) {
    showError('Todos los campos son obligatorios');
    return;
  }

  showOverlay();
  try {
    let result;
    if (mode === 'edit') {
      const id = Number(form.dataset.id);
      result = await updateRetentionCertificate(id, payload);
    } else {
      result = await createRetentionCertificate(payload);
    }
    if (!result.ok) {
      showError(result.error || 'Error al guardar');
      return;
    }
    const saved = normalizeCertificate(result.certificate);
    if (mode === 'edit') {
      certificates = certificates.map(cert => (cert.id === saved.id ? saved : cert));
    } else {
      certificates.push(saved);
    }
    renderCertificates();
    certModal.hide();
  } finally {
    hideOverlay();
  }
});

async function confirmDelete(cert) {
  if (!confirm('¿Eliminar certificado?')) return;
  showOverlay();
  try {
    const result = await deleteRetentionCertificate(cert.id);
    if (!result.ok) {
      alert(result.error || 'Error al eliminar');
      return;
    }
    certificates = certificates.filter(item => item.id !== cert.id);
    clearActionRow();
    renderCertificates();
  } finally {
    hideOverlay();
  }
}

addBtn.addEventListener('click', openCreateModal);
searchBox.addEventListener('input', renderCertificates);
amountInput.addEventListener('input', () => sanitizeDecimalInput(amountInput));
amountInput.addEventListener('blur', () => {
  const value = parseDecimal(amountInput.value);
  if (!value) {
    amountInput.value = '';
    return;
  }
  amountInput.value = formatCurrency(Math.abs(value));
});

if (isAdmin) {
  document.addEventListener('click', event => {
    if (!table.contains(event.target)) {
      clearActionRow();
    }
  });
}

loadCertificates();
