export function sanitizeDecimalInput(input) {
  if (!input) return;
  const cleaned = input.value.replace(/[^0-9,.-]/g, '');
  if (cleaned !== input.value) {
    input.value = cleaned;
  }
}

export function parseDecimal(value) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }
  if (value === null || value === undefined) return 0;
  const str = value.toString().trim();
  if (!str) return 0;
  const sanitized = str.replace(/[^0-9,.-]/g, '');
  if (!sanitized) return 0;
  const commaIndex = sanitized.lastIndexOf(',');
  const dotIndex = sanitized.lastIndexOf('.');
  let normalized = sanitized;
  if (commaIndex !== -1 && dotIndex !== -1) {
    if (commaIndex > dotIndex) {
      normalized = sanitized.replace(/\./g, '').replace(',', '.');
    } else {
      normalized = sanitized.replace(/,/g, '');
    }
  } else if (commaIndex !== -1) {
    normalized = sanitized.replace(',', '.');
  } else if (dotIndex !== -1) {
    const segments = sanitized.split('.');
    if (segments.length > 2) {
      const decimalPart = segments.pop();
      normalized = segments.join('') + '.' + decimalPart;
    } else {
      normalized = sanitized;
    }
  }
  if (normalized.includes('-')) {
    const negative = normalized.trim().startsWith('-');
    normalized = normalized.replace(/-/g, '');
    if (negative) {
      normalized = '-' + normalized;
    }
  }
  const num = Number(normalized);
  return Number.isFinite(num) ? num : 0;
}

export function formatCurrency(value) {
  const amount = Number(value);
  const safeAmount = Number.isFinite(amount) ? amount : 0;
  return safeAmount.toLocaleString('es-AR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}
