(function () {
  /* ── Matrix rain ──────────────────────────────────────────── */
  var CHARSET = '01アイウエカキクサシスタチツナニヌネハヒフヘマミムメラリルレ#$%*<>[]{}|_/\\!?NULLVOID';

  function buildSignal(length) {
    return Array.from({ length: length }, function () {
      return CHARSET[Math.floor(Math.random() * CHARSET.length)];
    }).join('\n');
  }

  function renderSignalRain(layer) {
    if (!(layer instanceof HTMLElement)) return;
    layer.innerHTML = '';

    var columnCount = window.innerWidth < 760 ? 18 : 32;

    for (var i = 0; i < columnCount; i++) {
      var column = document.createElement('div');
      var length = 20 + Math.floor(Math.random() * 22);

      column.className = 'signal-column' + (i % 7 === 0 ? ' is-amber' : '');
      column.textContent = buildSignal(length);
      column.style.left = (2 + i * (96 / columnCount)) + '%';
      column.style.animationDuration = (7 + Math.random() * 9) + 's';
      column.style.animationDelay = (-1 * Math.random() * 14) + 's';
      column.style.opacity = (0.22 + Math.random() * 0.28).toFixed(2);
      column.style.filter = 'blur(' + (Math.random() * 0.3).toFixed(2) + 'px)';

      layer.appendChild(column);
    }
  }

  var rainTimer;
  function scheduleRain() {
    window.clearTimeout(rainTimer);
    rainTimer = window.setTimeout(function () {
      document.querySelectorAll('[data-signal-rain]').forEach(renderSignalRain);
    }, 120);
  }

  document.querySelectorAll('[data-signal-rain]').forEach(renderSignalRain);
  window.addEventListener('resize', scheduleRain);

  /* ── Theme toggle (dark ↔ void) ───────────────────────────── */
  var body = document.body;
  var themeToggle = document.querySelector('[data-theme-toggle]');

  if (themeToggle) {
    themeToggle.addEventListener('click', function () {
      var current = body.getAttribute('data-theme');
      if (current === 'void') {
        body.removeAttribute('data-theme');
        localStorage.setItem('null-relay-theme', '');
      } else {
        body.setAttribute('data-theme', 'void');
        localStorage.setItem('null-relay-theme', 'void');
      }
    });
  }

  /* ── Chip groups ──────────────────────────────────────────── */
  document.querySelectorAll('[data-chip-group]').forEach(function (group) {
    group.addEventListener('click', function (event) {
      var target = event.target;
      if (!(target instanceof HTMLElement)) return;
      var chip = target.closest('[data-chip]');
      if (!(chip instanceof HTMLElement)) return;
      group.querySelectorAll('[data-chip]').forEach(function (item) {
        item.classList.remove('is-active');
      });
      chip.classList.add('is-active');
    });
  });

  /* ── Modal ────────────────────────────────────────────────── */
  var modal            = document.querySelector('[data-modal]');
  var modalTitle       = document.querySelector('[data-modal-title]');
  var modalPrice       = document.querySelector('[data-modal-price]');
  var modalOldPrice    = document.querySelector('[data-modal-old-price]');
  var modalDescription = document.querySelector('[data-modal-description]');
  var modalLocations   = document.querySelector('[data-modal-locations]');

  function closeModal() {
    if (modal instanceof HTMLElement) {
      modal.classList.remove('is-open');
    }
  }

  document.querySelectorAll('[data-open-product]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (!(modal instanceof HTMLElement)) return;

      var card = button.closest('[data-product-card]');
      if (!(card instanceof HTMLElement)) return;

      if (modalTitle)       modalTitle.textContent       = card.dataset.title       || 'UNKNOWN';
      if (modalPrice)       modalPrice.textContent       = card.dataset.price       || '0 ₽';
      if (modalOldPrice)    modalOldPrice.textContent    = card.dataset.oldPrice    || '';
      if (modalDescription) modalDescription.textContent = card.dataset.description || '';

      if (modalLocations) {
        modalLocations.innerHTML = '';
        var locations = (card.dataset.locations || '').split('|').filter(Boolean);
        locations.forEach(function (loc) {
          var li = document.createElement('li');
          li.innerHTML = '<span class="dot"></span><span>' + loc + '</span>';
          modalLocations.appendChild(li);
        });
      }

      modal.classList.add('is-open');
    });
  });

  document.querySelectorAll('[data-close-modal]').forEach(function (btn) {
    btn.addEventListener('click', closeModal);
  });

  if (modal instanceof HTMLElement) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeModal();
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeModal();
  });

  /* ── Chat room switching ──────────────────────────────────── */
  var chatRoomButtons = document.querySelectorAll('[data-chat-room]');
  var chatViews       = document.querySelectorAll('[data-chat-view]');

  function activateChatRoom(roomId) {
    chatRoomButtons.forEach(function (btn) {
      btn.classList.toggle('is-active', btn.dataset.chatRoom === roomId);
    });
    chatViews.forEach(function (view) {
      view.classList.toggle('is-hidden', view.dataset.chatView !== roomId);
    });
  }

  chatRoomButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      activateChatRoom(btn.dataset.chatRoom);
    });
  });

  /* ── Chat composer ────────────────────────────────────────── */
  var composerInput = document.querySelector('[data-composer-input]');
  var composerSend  = document.querySelector('[data-composer-send]');
  var messageFeed   = document.querySelector('[data-message-feed]');

  function sendMessage() {
    if (!(composerInput instanceof HTMLInputElement)) return;
    var text = composerInput.value.trim();
    if (!text) return;

    var now = new Date();
    var time = now.getHours().toString().padStart(2, '0') + ':' +
               now.getMinutes().toString().padStart(2, '0');

    var article = document.createElement('article');
    article.className = 'message-card mine';
    article.innerHTML =
      '<div class="message-meta">' +
        '<span class="message-author">you</span>' +
        '<span class="message-time">' + time + '</span>' +
      '</div>' +
      '<p>' + text.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</p>';

    if (messageFeed instanceof HTMLElement) {
      messageFeed.appendChild(article);
      messageFeed.scrollTop = messageFeed.scrollHeight;
    }

    composerInput.value = '';

    /* Fake operator reply after 2–4 seconds */
    window.setTimeout(function () {
      var replies = [
        'Запрос принят. Ожидайте подтверждения в чате покупки.',
        'Оператор на линии. Ответ в течение 10 минут.',
        'Баланс достаточен. Маршрут будет выдан автоматически.',
        'Уточните район и временной слот.',
        'Принято. Не дублируйте запрос.'
      ];
      var reply = replies[Math.floor(Math.random() * replies.length)];
      var replyTime = new Date();
      var rTime = replyTime.getHours().toString().padStart(2, '0') + ':' +
                  replyTime.getMinutes().toString().padStart(2, '0');

      var replyCard = document.createElement('article');
      replyCard.className = 'message-card tg';
      replyCard.innerHTML =
        '<div class="message-meta">' +
          '<span class="message-author">admin.null</span>' +
          '<span class="message-tag">TG</span>' +
          '<span class="message-time">' + rTime + '</span>' +
        '</div>' +
        '<p>' + reply + '</p>';

      if (messageFeed instanceof HTMLElement) {
        messageFeed.appendChild(replyCard);
        messageFeed.scrollTop = messageFeed.scrollHeight;
      }
    }, 2000 + Math.random() * 2000);
  }

  if (composerSend) {
    composerSend.addEventListener('click', sendMessage);
  }

  if (composerInput) {
    composerInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }
})();
