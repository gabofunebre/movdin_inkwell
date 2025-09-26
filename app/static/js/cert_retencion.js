import {
  fetchRetentionCertificates,
  createRetentionCertificate,
  updateRetentionCertificate,
  deleteRetentionCertificate,
  fetchRetainedTaxTypes
} from './api.js?v=3';
import { formatCurrency, showOverlay, hideOverlay } from './ui.js?v=2';
import { sanitizeDecimalInput, parseDecimal } from './money.js?v=1';
import { CURRENCY_SYMBOLS } from './constants.js';

const table = document.getElementById('cert-table');
const tbody = table.querySelector('tbody');
const addBtn = document.getElementById('add-certificate');
const searchBox = document.getElementById('search-box');
const modalEl = document.getElementById('certModal');
const certModal = new bootstrap.Modal(modalEl);
const filterBtn = document.getElementById('filter-button');
const filterModalEl = document.getElementById('certFilterModal');
const filterModal = filterModalEl ? new bootstrap.Modal(filterModalEl) : null;
const filterForm = document.getElementById('cert-filter-form');
const filterTaxTypeSelect = filterForm?.elements['filter_tax_type_id'] || null;
const clearFiltersBtn = document.getElementById('clear-filters');
const filterAlert = document.getElementById('filter-alert');
const filterSummary = document.getElementById('cert-filter-summary');
const filterSummaryItems = document.getElementById('cert-filter-summary-items');
const filterSummaryClear = document.getElementById('cert-filter-summary-clear');
const form = document.getElementById('cert-form');
const modalTitle = document.getElementById('cert-form-title');
const alertBox = document.getElementById('cert-alert');
const amountInput = form.amount;
const taxTypeSelect = form.elements['retained_tax_type_id'];
const isAdmin = Boolean(window.isAdmin);
const columnCount = table.querySelectorAll('thead th').length;
const currencyCode = window.certCurrency || 'ARS';
const currencySymbol = CURRENCY_SYMBOLS[currencyCode] || '';
const totalValueEl = document.getElementById('cert-total-value');

let certificates = [];
let retainedTaxTypes = [];
const filterState = {
  startDate: '',
  endDate: '',
  taxTypeId: ''
};
let activeActionRow = null;
let activeDataRow = null;

function formatFilterDate(value) {
  if (!value) return '';
  const parts = value.split('-');
  if (parts.length !== 3) return value;
  const [year, month, day] = parts;
  return `${day}/${month}/${year}`;
}

function getTaxTypeLabel(taxTypeId) {
  if (!taxTypeId) return '';
  const match = retainedTaxTypes.find(
    type => String(type.id) === String(taxTypeId)
  );
  if (match) {
    return match.name;
  }
  const certMatch = certificates.find(
    cert =>
      String(
        cert.retained_tax_type_id ?? cert.retained_tax_type?.id ?? cert.tax_type?.id
      ) === String(taxTypeId)
  );
  if (certMatch?.tax_type_name) {
    return certMatch.tax_type_name;
  }
  return `#${taxTypeId}`;
}

function updateFilterSummary() {
  if (!filterSummary || !filterSummaryItems) return;
  const chips = [];
  if (filterState.startDate) {
    chips.push({ label: 'Desde', value: formatFilterDate(filterState.startDate) });
  }
  if (filterState.endDate) {
    chips.push({ label: 'Hasta', value: formatFilterDate(filterState.endDate) });
  }
  if (filterState.taxTypeId) {
    chips.push({ label: 'Impuesto', value: getTaxTypeLabel(filterState.taxTypeId) });
  }

  filterSummaryItems.innerHTML = '';

  if (!chips.length) {
    filterSummary.classList.add('d-none');
    return;
  }

  const fragment = document.createDocumentFragment();
  chips.forEach(chipData => {
    const chip = document.createElement('span');
    chip.className = 'filter-summary-chip';
    const label = document.createElement('span');
    label.className = 'filter-summary-chip-label';
    label.textContent = `${chipData.label}:`;
    const value = document.createElement('span');
    value.textContent = chipData.value;
    chip.append(label, value);
    fragment.appendChild(chip);
  });

  filterSummaryItems.appendChild(fragment);
  filterSummary.classList.remove('d-none');
}

function clearCertificateFilters() {
  if (filterForm) {
    filterForm.reset();
    populateFilterTaxTypeSelect('');
  }
  filterState.startDate = '';
  filterState.endDate = '';
  filterState.taxTypeId = '';
  clearFilterError();
  renderCertificates();
  if (filterModal) {
    filterModal.hide();
  }
}

function normalizeCertificate(cert) {
  const taxType = cert.retained_tax_type ?? cert.tax_type ?? null;
  const taxTypeId =
    cert.retained_tax_type_id ?? (taxType ? taxType.id : null);
  const taxTypeName = taxType?.name ?? cert.withheld_tax ?? '';
  const numericTaxTypeId =
    typeof taxTypeId === 'number'
      ? taxTypeId
      : taxTypeId
      ? Number(taxTypeId)
      : null;
  return {
    ...cert,
    amount: Number(cert.amount),
    retained_tax_type: taxType ?? null,
    retained_tax_type_id: numericTaxTypeId,
    withheld_tax: taxTypeName,
    tax_type_name: taxTypeName
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

function populateTaxTypeSelect(selectedId = '', selectedType = null) {
  if (!taxTypeSelect) return;
  taxTypeSelect.innerHTML = '';
  taxTypeSelect.disabled = retainedTaxTypes.length === 0;
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Seleccione un impuesto retenido';
  placeholder.disabled = true;
  if (!selectedId) {
    placeholder.selected = true;
  }
  taxTypeSelect.appendChild(placeholder);
  const selectedValue = selectedId ? String(selectedId) : '';
  retainedTaxTypes.forEach(type => {
    const option = document.createElement('option');
    option.value = String(type.id);
    option.textContent = type.name;
    if (selectedValue && String(type.id) === selectedValue) {
      option.selected = true;
    }
    taxTypeSelect.appendChild(option);
  });
  if (selectedValue && !Array.from(taxTypeSelect.options).some(opt => opt.value === selectedValue)) {
    if (selectedType) {
      const opt = document.createElement('option');
      opt.value = selectedValue;
      opt.textContent = selectedType.name;
      opt.selected = true;
      taxTypeSelect.appendChild(opt);
    }
  }
}

function populateFilterTaxTypeSelect(selectedValue = '') {
  if (!filterTaxTypeSelect) return;
  const currentValue = selectedValue ? String(selectedValue) : '';
  filterTaxTypeSelect.innerHTML = '';
  const allOption = document.createElement('option');
  allOption.value = '';
  allOption.textContent = 'Todos';
  filterTaxTypeSelect.appendChild(allOption);
  retainedTaxTypes.forEach(type => {
    const option = document.createElement('option');
    option.value = String(type.id);
    option.textContent = type.name;
    if (currentValue && String(type.id) === currentValue) {
      option.selected = true;
    }
    filterTaxTypeSelect.appendChild(option);
  });
  if (
    currentValue &&
    !Array.from(filterTaxTypeSelect.options).some(option => option.value === currentValue)
  ) {
    const placeholder = document.createElement('option');
    placeholder.value = currentValue;
    placeholder.textContent = 'Seleccionado';
    placeholder.selected = true;
    filterTaxTypeSelect.appendChild(placeholder);
  }
}

function updateTaxTypeAvailability() {
  if (!addBtn) return;
  if (retainedTaxTypes.length === 0) {
    addBtn.disabled = true;
    addBtn.title = 'Configure tipos de impuestos retenidos antes de crear un certificado';
  } else {
    addBtn.disabled = false;
    addBtn.removeAttribute('title');
  }
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

function matchesFilters(cert) {
  if (filterState.startDate) {
    const certDate = new Date(cert.date);
    if (certDate < new Date(filterState.startDate)) {
      return false;
    }
  }
  if (filterState.endDate) {
    const certDate = new Date(cert.date);
    if (certDate > new Date(filterState.endDate)) {
      return false;
    }
  }
  if (filterState.taxTypeId) {
    const certTaxId =
      cert.retained_tax_type_id ??
      cert.retained_tax_type?.id ??
      cert.tax_type?.id ??
      null;
    if (!certTaxId || String(certTaxId) !== filterState.taxTypeId) {
      return false;
    }
  }
  return true;
}

function updateTotalDisplay(total) {
  if (!totalValueEl) return;
  totalValueEl.textContent = `${currencySymbol} ${formatCurrency(total)}`;
}

function renderCertificates() {
  const query = searchBox.value.trim().toLowerCase();
  const filtered = certificates.filter(cert => {
    if (!matchesFilters(cert)) {
      return false;
    }
    const number = cert.number?.toLowerCase() || '';
    const invoiceRef = cert.invoice_reference?.toLowerCase() || '';
    const taxType = cert.tax_type_name?.toLowerCase() || '';
    return (
      number.includes(query) ||
      invoiceRef.includes(query) ||
      taxType.includes(query)
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
  let totalAmount = 0;

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
    taxTd.textContent = cert.tax_type_name || '';

    const amountTd = document.createElement('td');
    amountTd.className = 'text-end';
    const amountValue = Number.isFinite(cert.amount) ? cert.amount : 0;
    const displayAmount = Math.abs(amountValue);
    amountTd.textContent = `${currencySymbol} ${formatCurrency(displayAmount)}`;
    totalAmount += displayAmount;

    tr.append(numberTd, dateTd, refTd, taxTd, amountTd);
    if (isAdmin) {
      tr.classList.add('cert-row-actionable');
      tr.addEventListener('click', () => toggleActionRow(tr, cert));
    }

    tbody.appendChild(tr);
  });

  updateTotalDisplay(totalAmount);
  updateFilterSummary();
}

function setDateLimits() {
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
}

function setFilterDateLimits() {
  if (!filterForm) return;
  const today = new Date().toISOString().split('T')[0];
  if (filterForm.start_date) {
    filterForm.start_date.max = today;
  }
  if (filterForm.end_date) {
    filterForm.end_date.max = today;
  }
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
  populateTaxTypeSelect();
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
  const selectedType = cert.retained_tax_type ?? cert.tax_type ?? null;
  const selectedId =
    cert.retained_tax_type_id ?? (selectedType ? selectedType.id : '');
  populateTaxTypeSelect(
    selectedId === null || selectedId === undefined ? '' : String(selectedId),
    selectedType
  );
  amountInput.value = formatCurrency(Math.abs(Number(cert.amount)));
  clearError();
  certModal.show();
}

async function loadData() {
  showOverlay();
  try {
    const [certData, taxData] = await Promise.all([
      fetchRetentionCertificates(200, 0),
      fetchRetainedTaxTypes()
    ]);
    retainedTaxTypes = Array.isArray(taxData) ? taxData : [];
    const currentSelection = taxTypeSelect ? taxTypeSelect.value : '';
    populateTaxTypeSelect(currentSelection);
    populateFilterTaxTypeSelect(filterState.taxTypeId);
    updateTaxTypeAvailability();
    certificates = Array.isArray(certData)
      ? certData.map(normalizeCertificate)
      : [];
    renderCertificates();
  } finally {
    hideOverlay();
  }
}

function clearFilterError() {
  if (!filterAlert) return;
  filterAlert.classList.add('d-none');
  filterAlert.textContent = '';
}

function showFilterError(message) {
  if (!filterAlert) return;
  filterAlert.textContent = message;
  filterAlert.classList.remove('d-none');
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
    invoice_reference: form.invoice_reference.value.trim()
  };

  const selectedTaxTypeId = taxTypeSelect ? taxTypeSelect.value : '';

  const amountValue = parseDecimal(amountInput.value);
  if (!Number.isFinite(amountValue) || amountValue <= 0) {
    showError('Ingrese un monto válido');
    return;
  }
  payload.amount = Math.abs(amountValue).toFixed(2);

  if (
    !payload.number ||
    !payload.invoice_reference ||
    !payload.date
  ) {
    showError('Todos los campos son obligatorios');
    return;
  }

  if (!selectedTaxTypeId) {
    showError('Seleccione un impuesto retenido');
    return;
  }

  payload.retained_tax_type_id = Number(selectedTaxTypeId);

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
  const confirmed = await showConfirmModal('¿Eliminar certificado?', {
    confirmText: 'Eliminar'
  });
  if (!confirmed) return;
  showOverlay();
  try {
    const result = await deleteRetentionCertificate(cert.id);
    if (!result.ok) {
      showAlertModal(result.error || 'Error al eliminar', {
        title: 'Error',
        confirmClass: 'btn-danger'
      });
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

if (filterBtn && filterModal) {
  filterBtn.addEventListener('click', () => {
    if (!filterForm) return;
    setFilterDateLimits();
    filterForm.start_date.value = filterState.startDate || '';
    filterForm.end_date.value = filterState.endDate || '';
    populateFilterTaxTypeSelect(filterState.taxTypeId);
    clearFilterError();
    filterModal.show();
  });
}

if (filterForm) {
  filterForm.addEventListener('submit', event => {
    event.preventDefault();
    clearFilterError();
    const startDate = filterForm.start_date.value;
    const endDate = filterForm.end_date.value;
    const selectedTaxType = filterTaxTypeSelect ? filterTaxTypeSelect.value : '';

    if (startDate && endDate && new Date(startDate) > new Date(endDate)) {
      showFilterError('La fecha inicio no puede ser posterior a la fecha fin');
      return;
    }

    filterState.startDate = startDate;
    filterState.endDate = endDate;
    filterState.taxTypeId = selectedTaxType;
    renderCertificates();
    if (filterModal) {
      filterModal.hide();
    }
  });
}

if (clearFiltersBtn) {
  clearFiltersBtn.addEventListener('click', () => {
    clearCertificateFilters();
  });
}

if (filterSummaryClear) {
  filterSummaryClear.addEventListener('click', event => {
    event.preventDefault();
    clearCertificateFilters();
  });
}

updateTaxTypeAvailability();
updateTotalDisplay(0);
loadData();
