import { updateInvoice } from './api.js?v=2';
import { showOverlay, hideOverlay } from './ui.js?v=2';
import { sanitizeDecimalInput, parseDecimal, formatCurrency } from './money.js?v=1';

function formatTaxAmount(value) {
  const amount = Number.isFinite(value) ? value : 0;
  return formatCurrency(amount);
}

function isManualPercent(percentInput) {
  return percentInput?.dataset.manual === 'true';
}

function showManualPlaceholder(percentInput) {
  if (!percentInput) return;
  percentInput.placeholder = 'MOD';
  percentInput.classList.add('manual-value');
}

function hideManualPlaceholder(percentInput) {
  if (!percentInput) return;
  percentInput.placeholder = '';
  percentInput.classList.remove('manual-value');
}

function setManualPercent(percentInput, amountInput, percentValue) {
  if (!percentInput || !amountInput) return;
  percentInput.dataset.manual = 'true';
  percentInput.dataset.manualPercent = String(percentValue ?? 0);
  percentInput.value = '';
  showManualPlaceholder(percentInput);
  amountInput.dataset.manual = 'true';
}

function clearManualPercent(percentInput, amountInput, fallbackPercent = null) {
  if (!percentInput || !amountInput) return;
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
  if (!percentInput) return 0;
  if (isManualPercent(percentInput)) {
    return parseDecimal(percentInput.dataset.manualPercent);
  }
  return parseDecimal(percentInput.value);
}

function getAmountValue(amountInput) {
  if (!amountInput) return 0;
  return Math.abs(parseDecimal(amountInput.value));
}

function roundToTwo(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  return Math.round((num + Number.EPSILON) * 100) / 100;
}

const form = document.getElementById('inv-form');
if (!form) {
  throw new Error('Invoice form not found');
}

const alertBox = document.getElementById('inv-alert');
const amountInput = form.amount;
const ivaPercentInput = form.iva_percent;
const ivaAmountInput = form.iva_amount;
const iibbPercentInput = form.iibb_percent;
const iibbAmountInput = form.iibb_amount;
const iibbRow = document.getElementById('iibb-row');
const retRow = document.getElementById('ret-row');
const percepcionesInput = form.percepciones;
const billingAccountLabel = document.getElementById('billing-account');

const modalEl = document.getElementById('invModal');
let invModal = null;

const invoiceDataEl = document.getElementById('invoice-data');
const accountDataEl = document.getElementById('account-data');
let invoice = invoiceDataEl ? JSON.parse(invoiceDataEl.textContent) : null;
const account = accountDataEl ? JSON.parse(accountDataEl.textContent) : null;

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

  if (!iibbPercentInput || !iibbAmountInput || iibbPercentInput.disabled) {
    if (iibbAmountInput) {
      iibbAmountInput.value = formatTaxAmount(0);
    }
    if (iibbPercentInput) {
      clearManualPercent(iibbPercentInput, iibbAmountInput);
    }
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

function toNumberString(value) {
  if (value === null || value === undefined || value === '') return '';
  const num = parseDecimal(value);
  return Number.isFinite(num) ? String(num) : '';
}

function populateForm(inv, acc) {
  if (!inv) return;
  form.dataset.invoiceId = inv.id;
  form.dataset.type = inv.type;
  form.date.value = inv.date || '';
  form.number.value = inv.number || '';
  form.description.value = inv.description || '';
  const amountRaw = inv.amount ?? '';
  const hasAmountValue = String(amountRaw).trim() !== '';
  if (hasAmountValue) {
    const baseAmount = Math.abs(parseDecimal(amountRaw));
    amountInput.value = formatTaxAmount(baseAmount);
  } else {
    amountInput.value = '';
  }
  const ivaPercent = toNumberString(inv.iva_percent);
  const ivaAmount = parseDecimal(inv.iva_amount ?? 0);
  clearManualPercent(ivaPercentInput, ivaAmountInput, ivaPercent);
  ivaPercentInput.value = ivaPercent;
  ivaAmountInput.value = formatTaxAmount(ivaAmount);
  if (iibbPercentInput && iibbAmountInput) {
    const iibbPercent = toNumberString(inv.iibb_percent ?? 0);
    const iibbAmount = parseDecimal(inv.iibb_amount ?? 0);
    clearManualPercent(iibbPercentInput, iibbAmountInput, iibbPercent);
    iibbPercentInput.value = iibbPercent;
    iibbAmountInput.value = formatTaxAmount(iibbAmount);
  }
  if (percepcionesInput) {
    const percAmount = parseDecimal(inv.percepciones ?? 0);
    percepcionesInput.value = formatTaxAmount(percAmount);
    percepcionesInput.disabled = inv.type !== 'purchase';
  }
  form.account_id.value = inv.account_id ?? form.account_id.value;
  if (billingAccountLabel && acc) {
    billingAccountLabel.textContent = acc.name || '';
    billingAccountLabel.style.color = acc.color || '';
  }
  const isPurchase = inv.type === 'purchase';
  if (retRow) {
    retRow.classList.toggle('d-none', !isPurchase);
  }
  if (iibbRow) {
    iibbRow.classList.toggle('d-none', isPurchase);
  }
  if (iibbPercentInput) {
    iibbPercentInput.disabled = isPurchase;
  }
  if (percepcionesInput && !isPurchase) {
    percepcionesInput.value = formatTaxAmount(0);
  }
  if (iibbAmountInput) {
    iibbAmountInput.disabled = isPurchase;
    if (isPurchase) {
      iibbAmountInput.value = formatTaxAmount(0);
    }
  }
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  alertBox.classList.add('d-none');
  recalcTaxes();
}

if (modalEl && invoice) {
  invModal = new bootstrap.Modal(modalEl);
  const editBtn = document.getElementById('edit-btn');
  if (editBtn) {
    editBtn.addEventListener('click', () => {
      populateForm(invoice, account);
      invModal.show();
    });
  }
} else if (invoice) {
  populateForm(invoice, account);
} else {
  const fallback = {
    id: form.dataset.invoiceId,
    type: form.dataset.type,
    date: form.date.value,
    number: form.number.value,
    description: form.description.value,
    amount: parseDecimal(form.amount.value),
    iva_percent: parseDecimal(ivaPercentInput.value),
    iva_amount: parseDecimal(ivaAmountInput.value),
    iibb_percent: iibbPercentInput ? parseDecimal(iibbPercentInput.value) : 0,
    iibb_amount: iibbAmountInput ? parseDecimal(iibbAmountInput.value) : 0,
    percepciones: percepcionesInput ? parseDecimal(percepcionesInput.value) : 0,
    account_id: Number(form.account_id.value)
  };
  populateForm(fallback, account);
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

if (iibbPercentInput) {
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
}

if (iibbAmountInput) {
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
}

if (percepcionesInput) {
  percepcionesInput.addEventListener('input', () => {
    if (percepcionesInput.disabled) return;
    sanitizeDecimalInput(percepcionesInput);
  });

  percepcionesInput.addEventListener('blur', () => {
    if (percepcionesInput.disabled || !percepcionesInput.value.trim()) return;
    const value = getAmountValue(percepcionesInput);
    percepcionesInput.value = formatTaxAmount(value);
  });
}

form.addEventListener('submit', async e => {
  e.preventDefault();
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  const type = form.dataset.type;
  const amount = Math.abs(parseDecimal(data.get('amount')));
  const ivaPercentValue = roundToTwo(Math.abs(getPercentValue(ivaPercentInput)));
  const ivaAmountValue = roundToTwo(getAmountValue(ivaAmountInput));
  const iibbPercentValue =
    type === 'purchase' ? 0 : roundToTwo(Math.abs(getPercentValue(iibbPercentInput)));
  const iibbAmountValue = roundToTwo(getAmountValue(iibbAmountInput));
  const percepcionesValue = type === 'purchase' ? roundToTwo(getAmountValue(percepcionesInput)) : 0;
  const payload = {
    date: data.get('date'),
    number: data.get('number'),
    description: data.get('description'),
    amount,
    account_id: Number(data.get('account_id')),
    type,
    iva_percent: ivaPercentValue,
    iibb_percent: type === 'purchase' ? 0 : iibbPercentValue,
    percepciones: percepcionesValue
  };
  if (isManualPercent(ivaPercentInput)) {
    payload.iva_amount = ivaAmountValue;
  }
  if (type === 'purchase') {
    payload.iibb_amount = 0;
  } else if (isManualPercent(iibbPercentInput)) {
    payload.iibb_amount = iibbAmountValue;
  }
  if (type !== 'purchase') {
    payload.percepciones = 0;
  }
  const today = new Date().toISOString().split('T')[0];
  if (payload.date > today) {
    alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
    alertBox.classList.add('alert-danger');
    alertBox.textContent = 'La fecha no puede ser futura';
    return;
  }
  showOverlay();
  const result = await updateInvoice(form.dataset.invoiceId, payload);
  hideOverlay();
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    alertBox.classList.add('alert-success');
    alertBox.textContent = 'Factura guardada';
    setTimeout(() => {
      if (invModal) {
        invModal.hide();
        window.location.reload();
      } else {
        window.location.href = `/invoice/${form.dataset.invoiceId}`;
      }
    }, 1000);
  } else {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = result.error || 'Error al guardar';
  }
});
