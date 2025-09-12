import { CURRENCY_SYMBOLS } from './constants.js';

export function formatCurrency(value) {
  return Number(value).toLocaleString('es-AR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

export function renderTransaction(tbody, tx, accountMap, onEdit, onDelete) {
  const tr = document.createElement('tr');
  const isIncome = tx.amount >= 0;
  const amount = formatCurrency(Math.abs(tx.amount));
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
  const descStyle = isIncome ? '' : 'padding-left:2em';
  const amountClass = isIncome ? 'text-start' : 'text-end';
  const amountColor = isIncome ? 'rgb(40,150,20)' : 'rgb(170,10,10)';
  const concept = tx.number ? `${tx.number} - ${tx.description}` : tx.description;

  const dateTd = document.createElement('td');
  dateTd.className = 'text-center';
  dateTd.textContent = formattedDate;

  const descTd = document.createElement('td');
  descTd.className = descClass;
  if (descStyle) descTd.style = descStyle;
  descTd.textContent = concept;

  const amountTd = document.createElement('td');
  amountTd.className = amountClass;
  amountTd.style = `color:${amountColor}`;
  amountTd.textContent = `${symbol} ${amount}`;

  const accTd = document.createElement('td');
  accTd.className = 'text-center';
  accTd.style = `color:${accColor}`;

  const nameSpan = document.createElement('span');
  nameSpan.textContent = accName;
  accTd.appendChild(nameSpan);

  if (window.isAdmin) {
    const actionsSpan = document.createElement('span');
    actionsSpan.classList.add('tx-actions', 'd-none');
    actionsSpan.innerHTML =
      `<button class="btn btn-sm btn-outline-secondary me-2" data-action="edit"><i class="bi bi-pencil"></i></button>` +
      `<button class="btn btn-sm btn-outline-danger" data-action="delete"><i class="bi bi-trash"></i></button>`;
    accTd.appendChild(actionsSpan);

    tr.addEventListener('click', () => {
      const showing = !actionsSpan.classList.contains('d-none');
      tbody.querySelectorAll('span.tx-actions').forEach(el => {
        el.classList.add('d-none');
        const prev = el.previousElementSibling;
        if (prev) prev.classList.remove('d-none');
      });
      if (!showing) {
        nameSpan.classList.add('d-none');
        actionsSpan.classList.remove('d-none');
      }
    });

    actionsSpan.querySelector('[data-action="edit"]').addEventListener('click', e => {
      e.stopPropagation();
      if (onEdit) onEdit(tx);
    });
    actionsSpan.querySelector('[data-action="delete"]').addEventListener('click', e => {
      e.stopPropagation();
      if (onDelete) onDelete(tx);
    });
  } else {
    tr.addEventListener('click', () => {
      tbody.querySelectorAll('tr').forEach(r => r.classList.remove('selected'));
      tr.classList.add('selected');
    });
  }

  tr.append(dateTd, descTd, amountTd, accTd);
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
  const amountColor = inv.type === 'sale' ? 'rgb(40,150,20)' : 'rgb(170,10,10)';
  const amount = formatCurrency(Math.abs(totalWithIva));
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
