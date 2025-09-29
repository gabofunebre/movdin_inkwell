export function createFilterSummaryManager({
  container,
  itemsContainer,
  clearButton = null,
  onClear = null
}) {
  const elementsReady = Boolean(container) && Boolean(itemsContainer);

  const update = chips => {
    if (!elementsReady) return;

    itemsContainer.innerHTML = '';

    const validChips = Array.isArray(chips)
      ? chips.filter(
          chip =>
            chip &&
            chip.value !== undefined &&
            chip.value !== null &&
            chip.value !== ''
        )
      : [];

    if (!validChips.length) {
      container.classList.add('d-none');
      return;
    }

    const fragment = document.createDocumentFragment();

    validChips.forEach(({ label, value }) => {
      const chip = document.createElement('span');
      chip.className = 'filter-summary-chip';

      if (label) {
        const labelEl = document.createElement('span');
        labelEl.className = 'filter-summary-chip-label';
        labelEl.textContent = `${label}:`;
        chip.appendChild(labelEl);
      }

      const valueEl = document.createElement('span');
      valueEl.textContent = value;
      chip.appendChild(valueEl);

      fragment.appendChild(chip);
    });

    itemsContainer.appendChild(fragment);
    container.classList.remove('d-none');
  };

  const clear = () => {
    if (typeof onClear === 'function') {
      onClear();
    }
  };

  if (clearButton && typeof clearButton.addEventListener === 'function') {
    clearButton.addEventListener('click', event => {
      event.preventDefault();
      clear();
    });
  }

  return {
    update,
    clear
  };
}

