(function () {
  const roomFeed = document.querySelector('[data-room-feed]');
  const roomTitle = document.querySelector('[data-room-title]');
  const roomStatus = document.querySelector('[data-room-status]');

  const presets = {
    support: [
      { author: 'lead.admin', text: 'Support room собран как терминальная сцена после регистрации: статус, поток, контакты.' },
      { author: 'rvn.node.01', text: 'Нужен короткий маршрут и кто сейчас на линии.' },
      { author: 'lead.admin', text: 'Правый rail держит админов, bot и резервную комнату. Левая колонка меняет активный поток.' }
    ],
    contacts: [
      { author: 'relay.bot', text: 'Telegram bot остаётся точкой быстрого входа для FAQ и простых маршрутов.' },
      { author: 'matrix.fallback', text: 'Element room нужен как резервный и более структурный канал по темам.' },
      { author: 'lead.admin', text: 'Все handles здесь статические: это только mock визуальной схемы.' }
    ],
    team: [
      { author: 'shift.control', text: 'Командный поток объясняет роли, смены и условия в том же терминальном стиле.' },
      { author: 'rvn.node.01', text: 'Какой следующий шаг после просмотра условий?' },
      { author: 'shift.control', text: 'Переход в register сохраняет этот же ритм и завершает воронку без лишней смены интерфейса.' }
    ]
  };

  function renderMessages(name) {
    if (!(roomFeed instanceof HTMLElement)) {
      return;
    }

    roomFeed.innerHTML = '';
    (presets[name] || presets.support).forEach(function (message, index) {
      const article = document.createElement('article');
      article.className = 'message-card' + (index % 2 === 1 ? ' mine' : '');

      const author = document.createElement('span');
      author.className = 'message-author';
      author.textContent = message.author;

      const text = document.createElement('p');
      text.textContent = message.text;

      article.append(author, text);
      roomFeed.appendChild(article);
    });
  }

  document.querySelectorAll('[data-room-button]').forEach(function (button) {
    button.addEventListener('click', function () {
      document.querySelectorAll('[data-room-button]').forEach(function (item) {
        item.classList.remove('is-active');
      });

      button.classList.add('is-active');

      if (roomTitle instanceof HTMLElement) {
        roomTitle.textContent = button.getAttribute('data-room-title') || 'Room';
      }

      if (roomStatus instanceof HTMLElement) {
        roomStatus.textContent = button.getAttribute('data-room-status') || '';
      }

      renderMessages(button.getAttribute('data-room') || 'support');
    });
  });
})();