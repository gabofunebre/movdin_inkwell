import { fetchAccountBalances, fetchAccountSummary } from './api.js?v=1';
import { showOverlay, hideOverlay, formatCurrency } from './ui.js';
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
  let html = `<div class="text-start"><p><strong>Saldo inicial:</strong> ${symbol} ${formatCurrency(summary.opening_balance)}</p>`;
  html += `<p><strong>Ingresos:</strong> ${symbol} ${formatCurrency(summary.income_balance)}</p>`;
  html += `<p><strong>Egresos:</strong> ${symbol} ${formatCurrency(summary.expense_balance)}</p>`;
  if (summary.is_billing) {
    html += `<p><strong>IVA Compras:</strong> ${symbol} ${formatCurrency(summary.iva_purchases)}</p>`;
    html += `<p><strong>IVA Ventas:</strong> ${symbol} ${formatCurrency(summary.iva_sales)}</p>`;
    html += `<p><strong>IIBB:</strong> ${symbol} ${formatCurrency(summary.iibb)}</p>`;
  }
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
