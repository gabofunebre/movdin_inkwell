export async function fetchAccounts(includeInactive = false) {
  const res = await fetch(`/accounts?include_inactive=${includeInactive}`);
  return res.json();
}

export async function fetchTransactions(limit, offset) {
  const res = await fetch(`/transactions?limit=${limit}&offset=${offset}`);
  return res.json();
}

export async function fetchAccountBalances() {
  const res = await fetch('/accounts/balances');
  return res.json();
}

export async function createTransaction(payload) {
  const res = await fetch('/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function createAccount(payload) {
  const res = await fetch('/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const account = await res.json();
    return { ok: true, account };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function updateAccount(id, payload) {
  const res = await fetch(`/accounts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const account = await res.json();
    return { ok: true, account };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteAccount(id) {
  const res = await fetch(`/accounts/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function fetchFrequents() {
  const res = await fetch('/frequents');
  return res.json();
}

export async function createFrequent(payload) {
  const res = await fetch('/frequents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function updateFrequent(id, payload) {
  const res = await fetch(`/frequents/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteFrequent(id) {
  const res = await fetch(`/frequents/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}
