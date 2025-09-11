import { CURRENCY_SYMBOLS } from './constants.js';

export function renderTransaction(tbody, tx, accountMap) {
  const tr = document.createElement('tr');
  const isIncome = tx.amount >= 0;
  const amount = Math.abs(tx.amount).toFixed(2);
  const acc = accountMap[tx.account_id];
  const accName = acc ? acc.name : '';
  const accColor = acc ? acc.color : '';
  const currency = acc ? acc.currency : null;
  const symbol = currency ? CURRENCY_SYMBOLS[currency] || '' : '';
  const dateObj = new Date(tx.date);
  const formattedDate = dateObj
    .toLocaleDateString('es-ES', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    })
    .replace('.', '');
  const descClass = isIncome ? '' : 'fst-italic';
  const descStyle = isIncome ? '' : ' style="padding-left:2em"';
  const amountClass = isIncome ? 'text-start' : 'text-end';
  const amountColor = isIncome ? 'rgb(40,150,20)' : 'rgb(170,10,10)';
  const concept = tx.number ? `${tx.number} - ${tx.description}` : tx.description;
  tr.innerHTML =
    `<td class="text-center">${formattedDate}</td>` +
    `<td class="${descClass}"${descStyle}>${concept}</td>` +
    `<td class="${amountClass}" style="color:${amountColor}">${symbol} ${amount}</td>` +
    `<td class="text-center" style="color:${accColor}">${accName}</td>`;
  tr.addEventListener('click', () => {
    tbody.querySelectorAll('tr').forEach(r => r.classList.remove('selected'));
    tr.classList.add('selected');
  });
  tbody.appendChild(tr);
}

export function renderInvoice(tbody, inv, accountMap) {
  const tr = document.createElement('tr');
  const acc = accountMap[inv.account_id];
  const currency = acc ? acc.currency : null;
  const symbol = currency ? CURRENCY_SYMBOLS[currency] || '' : '';
  const dateObj = new Date(inv.date);
  const formattedDate = dateObj
    .toLocaleDateString('es-ES', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    })
    .replace('.', '');
  const typeText = inv.type === 'sale' ? 'Venta' : 'Compra';
  // Monto total calculado como importe sin impuestos más IVA
  const totalWithIva = Number(inv.amount) + Number(inv.iva_amount);
  const amountColor = totalWithIva >= 0 ? 'rgb(40,150,20)' : 'rgb(170,10,10)';
  const amount = Math.abs(totalWithIva).toFixed(2);
  tr.innerHTML =
    `<td class="text-center">${inv.number || ''}</td>` +
    `<td class="text-center">${formattedDate}</td>` +
    `<td class="text-center">${typeText}</td>` +
    `<td>${inv.description}</td>` +
    `<td class="text-end" style="color:${amountColor}">${symbol} ${amount}</td>`;
  tr.style.cursor = 'pointer';
  tr.addEventListener('click', () => {
    window.location.href = `/invoice/${inv.id}`;
  });
  tbody.appendChild(tr);
}

export function populateAccounts(select, accounts) {
  select.innerHTML = '';
  accounts.forEach(acc => {
    const opt = document.createElement('option');
    opt.value = acc.id;
    opt.textContent = `${acc.name} (${acc.currency})`;
    select.appendChild(opt);
  });
}

export function renderAccount(tbody, account, onEdit, onDelete) {
  const tr = document.createElement('tr');
  tr.classList.add('text-center');
  const nameColor = account.color || '#000000';
  tr.innerHTML =
    `<td style="color:${nameColor}">${account.name}</td>` +
    `<td>${account.currency}</td>` +
    `<td>${account.is_billing ? '<i class="bi bi-star-fill text-warning"></i>' : ''}</td>` +
    `<td class="text-nowrap">` +
    `<button class="btn btn-sm btn-outline-secondary me-2" title="Editar"><i class="bi bi-pencil"></i></button>` +
    `<button class="btn btn-sm btn-outline-danger" title="Eliminar"><i class="bi bi-x"></i></button>` +
    `</td>`;
  const [editBtn, delBtn] = tr.querySelectorAll('button');
  if (onEdit) editBtn.addEventListener('click', () => onEdit(account));
  if (onDelete) delBtn.addEventListener('click', () => onDelete(account));
  tbody.appendChild(tr);
}

export function renderFrequent(tbody, freq, onEdit, onDelete) {
  const tr = document.createElement('tr');
  tr.classList.add('text-center');
  tr.innerHTML =
    `<td>${freq.description}</td>` +
    `<td class="text-nowrap">` +
    `<button class="btn btn-sm btn-outline-secondary me-2" title="Editar"><i class="bi bi-pencil"></i></button>` +
    `<button class="btn btn-sm btn-outline-danger" title="Eliminar"><i class="bi bi-x"></i></button>` +
    `</td>`;
  const [editBtn, delBtn] = tr.querySelectorAll('button');
  if (onEdit) editBtn.addEventListener('click', () => onEdit(freq));
  if (onDelete) delBtn.addEventListener('click', () => onDelete(freq));
  tbody.appendChild(tr);
}

const overlayEl = document.getElementById('overlay');

export function showOverlay() {
  overlayEl.classList.remove('d-none');
}

export function hideOverlay() {
  overlayEl.classList.add('d-none');
}
