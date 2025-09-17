import {
  fetchRetentionCertificates,
  createRetentionCertificate,
  updateRetentionCertificate,
  deleteRetentionCertificate
} from './api.js?v=1';
import { formatCurrency, showOverlay, hideOverlay } from './ui.js?v=1';
import { sanitizeDecimalInput, parseDecimal } from './money.js?v=1';
import { CURRENCY_SYMBOLS } from './constants.js';

const tbody = document.querySelector('#cert-table tbody');
const addBtn = document.getElementById('add-certificate');
const searchBox = document.getElementById('search-box');
const modalEl = document.getElementById('certModal');
const certModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('cert-form');
const modalTitle = document.getElementById('cert-form-title');
const alertBox = document.getElementById('cert-alert');
const amountInput = form.amount;
const isAdmin = Boolean(window.isAdmin);
const currencyCode = window.certCurrency || 'ARS';
const currencySymbol = CURRENCY_SYMBOLS[currencyCode] || '';

let certificates = [];

function normalizeCertificate(cert) {
  return {
    ...cert,
    amount: Number(cert.amount)
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

function renderCertificates() {
  const query = searchBox.value.trim().toLowerCase();
  const filtered = certificates.filter(cert => {
    const number = cert.number?.toLowerCase() || '';
    const invoiceRef = cert.invoice_reference?.toLowerCase() || '';
    const concept = cert.concept?.toLowerCase() || '';
    return (
      number.includes(query) ||
      invoiceRef.includes(query) ||
      concept.includes(query)
    );
  });
  filtered.sort((a, b) => {
    if (a.date === b.date) {
      return b.id - a.id;
    }
    return new Date(b.date) - new Date(a.date);
  });
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

    const conceptTd = document.createElement('td');
    conceptTd.textContent = cert.concept;

    const amountTd = document.createElement('td');
    amountTd.className = 'text-end';
    const amountValue = Number.isFinite(cert.amount) ? cert.amount : 0;
    amountTd.textContent = `${currencySymbol} ${formatCurrency(Math.abs(amountValue))}`;

    tr.append(numberTd, dateTd, refTd, conceptTd, amountTd);

    if (isAdmin) {
      const actionsTd = document.createElement('td');
      actionsTd.className = 'text-center text-nowrap';

      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'btn btn-sm btn-outline-secondary me-2';
      editBtn.title = 'Editar';
      editBtn.innerHTML = '<i class="bi bi-pencil"></i>';
      editBtn.addEventListener('click', () => openEditModal(cert));

      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'btn btn-sm btn-outline-danger';
      deleteBtn.title = 'Eliminar';
      deleteBtn.innerHTML = '<i class="bi bi-x"></i>';
      deleteBtn.addEventListener('click', () => confirmDelete(cert));

      actionsTd.append(editBtn, deleteBtn);
      tr.appendChild(actionsTd);
    }

    tbody.appendChild(tr);
  });
}

function setDateLimits() {
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
}

function openCreateModal() {
  form.reset();
  modalTitle.textContent = 'Nuevo certificado';
  form.dataset.mode = 'create';
  delete form.dataset.id;
  setDateLimits();
  form.date.value = form.date.max;
  amountInput.value = '';
  clearError();
  certModal.show();
}

function openEditModal(cert) {
  form.reset();
  modalTitle.textContent = 'Editar certificado';
  form.dataset.mode = 'edit';
  form.dataset.id = cert.id;
  setDateLimits();
  form.date.value = cert.date;
  form.number.value = cert.number;
  form.invoice_reference.value = cert.invoice_reference;
  form.concept.value = cert.concept;
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
    concept: form.concept.value.trim()
  };

  const amountValue = parseDecimal(amountInput.value);
  if (!Number.isFinite(amountValue) || amountValue <= 0) {
    showError('Ingrese un monto válido');
    return;
  }
  payload.amount = Math.abs(amountValue).toFixed(2);

  if (!payload.number || !payload.invoice_reference || !payload.concept || !payload.date) {
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

loadCertificates();
