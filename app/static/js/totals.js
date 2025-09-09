import { fetchAccountBalances } from './api.js';
import { showOverlay, hideOverlay } from './ui.js';
import { CURRENCY_SYMBOLS } from './constants.js';

const tbody = document.querySelector('#totals-table tbody');
const refreshBtn = document.getElementById('refresh-totals');

function renderTotals(data) {
  tbody.innerHTML = '';
  data.forEach(acc => {
    const tr = document.createElement('tr');
    tr.classList.add('text-center');
    const total = Number(acc.balance).toFixed(2);
    const nameTd = document.createElement('td');
    nameTd.textContent = acc.name;
    nameTd.style.color = acc.color;
    const totalTd = document.createElement('td');
    const symbol = CURRENCY_SYMBOLS[acc.currency] || '';
    totalTd.textContent = `${symbol} ${total}`;
    tr.appendChild(nameTd);
    tr.appendChild(totalTd);
    tbody.appendChild(tr);
  });
}

async function loadTotals() {
  showOverlay();
  const data = await fetchAccountBalances();
  renderTotals(data);
  hideOverlay();
}

refreshBtn.addEventListener('click', loadTotals);

loadTotals();
