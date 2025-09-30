(() => {
  const modalElement = document.getElementById('app-message-modal');
  if (!modalElement) return;

  const modal = new bootstrap.Modal(modalElement);
  const titleElement = modalElement.querySelector('.modal-title');
  const bodyElement = modalElement.querySelector('.modal-body');
  const primaryButton = modalElement.querySelector('[data-modal-primary]');
  const secondaryButton = modalElement.querySelector('[data-modal-secondary]');

  function openModal({
    title = 'Aviso',
    message = '',
    html = null,
    confirmText = 'Aceptar',
    cancelText = 'Cancelar',
    showCancel = false,
    confirmClass = 'btn-primary',
    defaultValue = true
  }) {
    titleElement.textContent = title;
    if (html !== null && html !== undefined) {
      bodyElement.innerHTML = html;
    } else {
      const text = message === null || message === undefined ? '' : String(message);
      if (text.includes('\n')) {
        bodyElement.textContent = '';
        const lines = text.split('\n');
        lines.forEach((line, index) => {
          bodyElement.appendChild(document.createTextNode(line));
          if (index < lines.length - 1) {
            bodyElement.appendChild(document.createElement('br'));
          }
        });
      } else {
        bodyElement.textContent = text;
      }
    }
    primaryButton.textContent = confirmText;
    primaryButton.classList.remove('btn-primary', 'btn-danger', 'btn-success', 'btn-warning');
    primaryButton.classList.add(confirmClass);

    if (showCancel) {
      secondaryButton.textContent = cancelText;
      secondaryButton.classList.remove('d-none');
    } else {
      secondaryButton.classList.add('d-none');
    }

    return new Promise(resolve => {
      let resolved = false;

      const finish = value => {
        if (resolved) return;
        resolved = true;
        modalElement.removeEventListener('hidden.bs.modal', onHidden);
        primaryButton.removeEventListener('click', onConfirm);
        secondaryButton.removeEventListener('click', onCancelClick);
        resolve(value);
      };

      const onConfirm = () => {
        finish(true);
        modal.hide();
      };

      const onCancelClick = () => {
        finish(false);
        modal.hide();
      };

      const onHidden = () => {
        finish(defaultValue);
      };

      primaryButton.addEventListener('click', onConfirm);
      secondaryButton.addEventListener('click', onCancelClick);
      modalElement.addEventListener('hidden.bs.modal', onHidden);

      modal.show();
    });
  }

  window.showAlertModal = function (message, options = {}) {
    const {
      title = 'Aviso',
      confirmText = 'Aceptar',
      confirmClass = 'btn-primary',
      defaultValue = true,
      html = null
    } = options;
    return openModal({
      title,
      message,
      html,
      confirmText,
      confirmClass,
      showCancel: false,
      defaultValue
    });
  };

  window.showConfirmModal = function (message, options = {}) {
    const {
      title = 'Confirmación',
      confirmText = 'Aceptar',
      cancelText = 'Cancelar',
      confirmClass = 'btn-danger',
      defaultValue = false,
      html = null
    } = options;
    return openModal({
      title,
      message,
      html,
      confirmText,
      cancelText,
      confirmClass,
      showCancel: true,
      defaultValue
    });
  };

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const message = form.dataset.confirm;
    if (!message) return;

    event.preventDefault();
    showConfirmModal(message, {
      title: form.dataset.confirmTitle,
      confirmText: form.dataset.confirmConfirmText || 'Aceptar',
      cancelText: form.dataset.confirmCancelText || 'Cancelar',
      confirmClass: form.dataset.confirmClass || 'btn-danger'
    }).then(confirmed => {
      if (confirmed) {
        form.submit();
      }
    });
  });
})();
