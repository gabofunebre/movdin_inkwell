export async function fetchAccounts(includeInactive = false) {
  const res = await fetch(`/accounts?include_inactive=${includeInactive}`);
  return res.json();
}

export async function fetchTransactions(options = {}) {
  const params = new URLSearchParams();
  const pageCandidate = Number.parseInt(options.page, 10);
  const page = Number.isFinite(pageCandidate) && pageCandidate > 0 ? pageCandidate : 1;
  const limitCandidate = Number.parseInt(options.limit, 10);
  const limit = Number.isFinite(limitCandidate) && limitCandidate > 0 ? limitCandidate : 50;
  params.set('page', String(page));
  params.set('limit', String(limit));

  const search = options.search?.toString().trim();
  if (search) {
    params.set('search', search);
  }
  if (options.startDate) {
    params.set('start_date', options.startDate);
  }
  if (options.endDate) {
    params.set('end_date', options.endDate);
  }
  if (options.accountId !== undefined && options.accountId !== null && options.accountId !== '') {
    params.set('account_id', String(options.accountId));
  }

  const query = params.toString();
  const res = await fetch(`/transactions${query ? `?${query}` : ''}`);
  if (!res.ok) {
    let error = 'No se pudieron obtener los movimientos';
    try {
      const data = await res.json();
      error = data?.detail || data?.message || error;
    } catch (_) {}
    throw new Error(error);
  }

  const data = await res.json();
  const items = Array.isArray(data?.items) ? data.items : [];
  const total = Number.isFinite(data?.total)
    ? data.total
    : Number.parseInt(data?.total, 10) || 0;
  const hasMoreRaw =
    typeof data?.has_more !== 'undefined'
      ? data.has_more
      : data?.hasMore;
  const responsePageCandidate = Number.parseInt(data?.page, 10);
  const responsePage = Number.isFinite(responsePageCandidate) && responsePageCandidate > 0
    ? responsePageCandidate
    : page;
  const responseLimitCandidate = Number.parseInt(data?.limit, 10);
  const responseLimit = Number.isFinite(responseLimitCandidate) && responseLimitCandidate > 0
    ? responseLimitCandidate
    : limit;

  return {
    items,
    total,
    hasMore: Boolean(hasMoreRaw),
    page: responsePage,
    limit: responseLimit,
  };
}

export async function fetchNotifications(options = {}) {
  const params = new URLSearchParams();
  if (options.status) params.set('status', options.status);
  if (options.since) params.set('since', options.since);
  if (options.topic) params.set('topic', options.topic);
  if (options.type) params.set('type', options.type);
  if (typeof options.limit === 'number') params.set('limit', String(options.limit));
  if (options.cursor) params.set('cursor', options.cursor);
  if (options.include) {
    const includeValue = Array.isArray(options.include)
      ? options.include.join(',')
      : String(options.include);
    if (includeValue) params.set('include', includeValue);
  }
  const query = params.toString();
  const res = await fetch(`/notificaciones${query ? `?${query}` : ''}`);
  if (!res.ok) {
    let error = 'No se pudieron obtener las notificaciones';
    try {
      const data = await res.json();
      error = data?.detail || data?.message || error;
    } catch (_) {}
    throw new Error(error);
  }
  return res.json();
}

export async function fetchInvoices(limit, offset) {
  const res = await fetch(`/invoices?limit=${limit}&offset=${offset}`);
  return res.json();
}

export async function fetchRetentionCertificates(limit, offset) {
  const res = await fetch(`/retention-certificates?limit=${limit}&offset=${offset}`);
  return res.json();
}

export async function fetchAccountBalances() {
  const res = await fetch('/accounts/balances');
  return res.json();
}

export async function fetchAccountSummary(id) {
  const res = await fetch(`/accounts/${id}/summary`);
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

export async function updateTransaction(id, payload) {
  const res = await fetch(`/transactions/${id}`, {
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

export async function deleteTransaction(id) {
  const res = await fetch(`/transactions/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function acknowledgeNotification(id) {
  try {
    const res = await fetch('/notificaciones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'ack', id })
    });
    let data = null;
    try {
      data = await res.clone().json();
    } catch (_) {}
    if (res.ok) return { ok: true, data };
    let error = 'No se pudo confirmar la notificación';
    if (data) {
      error = data.detail || data.message || error;
    }
    return { ok: false, error };
  } catch (err) {
    const message = err?.message && String(err.message).trim();
    return {
      ok: false,
      error: message || 'No se pudo confirmar la notificación'
    };
  }
}

export async function syncBillingTransactions() {
  try {
    const res = await fetch('/transactions/billing/sync', { method: 'POST' });
    let data = null;
    let rawText = null;
    try {
      data = await res.clone().json();
    } catch (_) {
      try {
        rawText = await res.clone().text();
      } catch (_) {}
    }
    if (res.ok) return { ok: true, data: data ?? rawText };
    const statusInfo = res.statusText
      ? `${res.status} ${res.statusText}`.trim()
      : res.status
      ? `Código ${res.status}`
      : null;
    const rawTextTrimmed =
      typeof rawText === 'string' ? rawText.trim() : null;
    let plainRawText = null;
    if (rawTextTrimmed) {
      const htmlIndicatorPatterns = [
        /<!doctype/i,
        /<\s*html[\s>]/i,
        /<\s*\/\s*html[\s>]/i,
        /<\s*body[\s>]/i,
        /<\s*\/\s*body[\s>]/i,
        /<\s*head[\s>]/i,
        /<\s*\/\s*head[\s>]/i,
        /<\?xml/i
      ];
      const containsHtmlIndicator = htmlIndicatorPatterns.some(pattern =>
        pattern.test(rawTextTrimmed)
      );
      const closingTagPattern = /<\s*\/\s*(?:html|body|head)\b[^>]*>/i;
      const hasClosingTag = closingTagPattern.test(rawTextTrimmed);
      if (!containsHtmlIndicator && !hasClosingTag) {
        plainRawText = rawTextTrimmed;
      }
    }
    const errorDetail =
      data?.detail ||
      data?.message ||
      (typeof data === 'string' ? data : null) ||
      plainRawText ||
      statusInfo;
    return {
      ok: false,
      error:
        errorDetail ||
        'No se pudieron obtener los movimientos de la cuenta de facturación'
    };
  } catch (err) {
    const baseMessage =
      'No se pudieron obtener los movimientos de la cuenta de facturación';
    const messageFromError = err?.message && String(err.message).trim();
    return {
      ok: false,
      error: messageFromError
        ? `${baseMessage}: ${messageFromError}`
        : baseMessage
    };
  }
}

export async function createInvoice(payload) {
  const res = await fetch('/invoices', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    if (Array.isArray(data.detail)) {
      error = data.detail.map(d => d.msg).join(', ');
    } else {
      error = data.detail || error;
    }
  } catch (_) {}
  return { ok: false, error };
}

export async function updateInvoice(id, payload) {
  const res = await fetch(`/invoices/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    if (Array.isArray(data.detail)) {
      error = data.detail.map(d => d.msg).join(', ');
    } else {
      error = data.detail || error;
    }
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteInvoice(id) {
  const res = await fetch(`/invoices/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function createRetentionCertificate(payload) {
  const res = await fetch('/retention-certificates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const certificate = await res.json();
    return { ok: true, certificate };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    if (Array.isArray(data.detail)) {
      error = data.detail.map(d => d.msg).join(', ');
    } else {
      error = data.detail || error;
    }
  } catch (_) {}
  return { ok: false, error };
}

export async function updateRetentionCertificate(id, payload) {
  const res = await fetch(`/retention-certificates/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const certificate = await res.json();
    return { ok: true, certificate };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    if (Array.isArray(data.detail)) {
      error = data.detail.map(d => d.msg).join(', ');
    } else {
      error = data.detail || error;
    }
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteRetentionCertificate(id) {
  const res = await fetch(`/retention-certificates/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function createAccount(payload, replaceBilling = false) {
  const res = await fetch(`/accounts?replace_billing=${replaceBilling}`, {
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

export async function updateAccount(id, payload, replaceBilling = false) {
  const res = await fetch(`/accounts/${id}?replace_billing=${replaceBilling}`, {
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

export async function fetchRetainedTaxTypes() {
  const res = await fetch('/retained-tax-types');
  return res.json();
}

export async function createRetainedTaxType(payload) {
  const res = await fetch('/retained-tax-types', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const taxType = await res.json();
    return { ok: true, taxType };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function updateRetainedTaxType(id, payload) {
  const res = await fetch(`/retained-tax-types/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const taxType = await res.json();
    return { ok: true, taxType };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteRetainedTaxType(id) {
  const res = await fetch(`/retained-tax-types/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}
