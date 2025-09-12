import { updateInvoice } from './api.js?v=1';
import { showOverlay, hideOverlay, formatCurrency } from './ui.js?v=1';

const modalEl = document.getElementById('invModal');
if (modalEl) {
  const invModal = new bootstrap.Modal(modalEl);
  const form = document.getElementById('inv-form');
  const alertBox = document.getElementById('inv-alert');
  const amountInput = form.amount;
  const ivaPercentInput = form.iva_percent;
  const ivaAmountInput = form.iva_amount;
  const iibbPercentInput = form.iibb_percent;
  const iibbAmountInput = form.iibb_amount;
  const iibbRow = document.getElementById('iibb-row');
  const billingAccountLabel = document.getElementById('billing-account');

  const invoice = JSON.parse(document.getElementById('invoice-data').textContent);
  const account = JSON.parse(document.getElementById('account-data').textContent);

  document.getElementById('edit-btn').addEventListener('click', () => {
    populateForm();
    invModal.show();
  });

  function populateForm() {
    form.dataset.invoiceId = invoice.id;
    form.dataset.type = invoice.type;
    form.date.value = invoice.date;
    form.number.value = invoice.number || '';
    form.description.value = invoice.description || '';
    form.amount.value = invoice.amount;
    form.iva_percent.value = invoice.iva_percent;
    form.iibb_percent.value = invoice.iibb_percent || 0;
    form.account_id.value = invoice.account_id;
    billingAccountLabel.textContent = account.name;
    billingAccountLabel.style.color = account.color;
    const isPurchase = invoice.type === 'purchase';
    iibbRow.classList.toggle('d-none', isPurchase);
    iibbPercentInput.disabled = isPurchase;
    iibbAmountInput.disabled = isPurchase;
    const today = new Date().toISOString().split('T')[0];
    form.date.max = today;
    recalcTaxes();
    alertBox.classList.add('d-none');
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

  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const amount = Math.abs(parseFloat(data.get('amount')));
    const type = form.dataset.type;
    const payload = {
      date: data.get('date'),
      number: data.get('number'),
      description: data.get('description'),
      amount,
      account_id: Number(data.get('account_id')),
      type,
      iva_percent: parseFloat(data.get('iva_percent')) || 0,
      iibb_percent: type === 'purchase' ? 0 : parseFloat(data.get('iibb_percent')) || 0
    };
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
        invModal.hide();
        window.location.reload();
      }, 1000);
    } else {
      alertBox.classList.add('alert-danger');
      alertBox.textContent = result.error || 'Error al guardar';
    }
  });
}
