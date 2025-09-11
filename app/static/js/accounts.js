import { fetchAccountBalances, fetchAccountSummary } from './api.js?v=1';
import { showOverlay, hideOverlay } from './ui.js';
import { CURRENCY_SYMBOLS } from './constants.js';

const tbody = document.querySelector('#accounts-table tbody');
const refreshBtn = document.getElementById('refresh-accounts');

function renderAccounts(data) {
  tbody.innerHTML = '';
  data.forEach(acc => {
    const tr = document.createElement('tr');
    tr.classList.add('text-center');
    tr.dataset.accountId = acc.account_id;
    const total = Number(acc.balance).toFixed(2);
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
  let html = `<div class="text-start"><p><strong>Saldo inicial:</strong> ${symbol} ${Number(summary.opening_balance).toFixed(2)}</p>`;
  html += `<p><strong>Ingresos:</strong> ${symbol} ${Number(summary.income_balance).toFixed(2)}</p>`;
  html += `<p><strong>Egresos:</strong> ${symbol} ${Number(summary.expense_balance).toFixed(2)}</p>`;
  if (summary.is_billing) {
    html += `<p><strong>IVA Compras:</strong> ${symbol} ${Number(summary.iva_purchases).toFixed(2)}</p>`;
    html += `<p><strong>IVA Ventas:</strong> ${symbol} ${Number(summary.iva_sales).toFixed(2)}</p>`;
    html += `<p><strong>IIBB:</strong> ${symbol} ${Number(summary.iibb).toFixed(2)}</p>`;
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
