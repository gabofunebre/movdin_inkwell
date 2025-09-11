import { fetchAccountBalances, fetchAccountSummary } from './api.js?v=1';
import { showOverlay, hideOverlay, formatCurrency } from './ui.js?v=1';
import { CURRENCY_SYMBOLS } from './constants.js';

const tbody = document.querySelector('#accounts-table tbody');
const refreshBtn = document.getElementById('refresh-accounts');

function renderAccounts(data) {
  tbody.innerHTML = '';
  data.forEach(acc => {
    const tr = document.createElement('tr');
    tr.classList.add('text-center');
    tr.dataset.accountId = acc.account_id;
    const total = formatCurrency(acc.balance);
    const nameTd = document.createElement('td');
    nameTd.textContent = acc.name;
    nameTd.style.color = acc.color;
    const totalTd = document.createElement('td');
    const symbol = CURRENCY_SYMBOLS[acc.currency] || '';
    totalTd.textContent = `${symbol} ${total}`;
    totalTd.classList.add('fw-bold', 'fs-5');
    tr.appendChild(nameTd);
    tr.appendChild(totalTd);
    tr.addEventListener('click', () => toggleDetails(tr, acc));
    tbody.appendChild(tr);
  });
}

async function toggleDetails(row, acc) {
  const next = row.nextElementSibling;
  if (next && next.classList.contains('details')) {
    next.remove();
    return;
  }
  const existing = tbody.querySelector('.details');
  if (existing) existing.remove();
  showOverlay();
  const summary = await fetchAccountSummary(acc.account_id);
  hideOverlay();
  const symbol = CURRENCY_SYMBOLS[acc.currency] || '';
  const detailTr = document.createElement('tr');
  detailTr.classList.add('details');
  const detailTd = document.createElement('td');
  detailTd.colSpan = 2;

  const balance =
    Number(summary.opening_balance) +
    Number(summary.income_balance) -
    Number(summary.expense_balance);
  const ivaBalance = summary.is_billing
    ? Number(summary.iva_purchases) - Number(summary.iva_sales)
    : 0;
  const total = summary.is_billing
    ? balance + ivaBalance - Number(summary.iibb)
    : balance;

  let html = '<div class="container text-start">';
  html += '<div class="row">';
  html += '<div class="col">';
  html += `<p><strong>Saldo inicial:</strong> <span class="text-info">${symbol} ${formatCurrency(summary.opening_balance)}</span></p>`;
  html += `<p><strong>Ingresos:</strong> <span class="text-success">${symbol} ${formatCurrency(summary.income_balance)}</span></p>`;
  html += `<p><strong>Egresos:</strong> <span class="text-danger">${symbol} ${formatCurrency(summary.expense_balance)}</span></p>`;
  html += `<p><strong>Balance:</strong> <span class="text-dark fst-italic">${symbol} ${formatCurrency(balance)}</span></p>`;
  html += '</div>';
  if (summary.is_billing) {
    html += '<div class="col">';
    html += `<p><strong>IVA Compras:</strong> <span class="text-success">${symbol} ${formatCurrency(summary.iva_purchases)}</span></p>`;
    html += `<p><strong>IVA Ventas:</strong> <span class="text-danger">${symbol} ${formatCurrency(summary.iva_sales)}</span></p>`;
    html += `<p><strong>Balance IVA:</strong> <span class="text-dark fst-italic">${symbol} ${formatCurrency(ivaBalance)}</span></p>`;
    html += `<p><strong>IIBB:</strong> <span class="text-danger">${symbol} ${formatCurrency(summary.iibb)}</span></p>`;
    html += '</div>';
  }
  html += '</div>';
  html += `<div class="row"><div class="col text-center"><p class="mb-0"><strong>Total Disponible:</strong> <span class="text-dark fw-bold fs-5">${symbol} ${formatCurrency(total)}</span></p></div></div>`;
  html += '</div>';
  detailTd.innerHTML = html;
  detailTr.appendChild(detailTd);
  row.after(detailTr);
}

async function loadAccounts() {
  showOverlay();
  const data = await fetchAccountBalances();
  renderAccounts(data);
  hideOverlay();
}

refreshBtn.addEventListener('click', loadAccounts);

loadAccounts();
