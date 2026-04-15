(function () {
  const roomFeed = document.querySelector('[data-room-feed]');
  const roomTitle = document.querySelector('[data-room-title]');
  const roomStatus = document.querySelector('[data-room-status]');

  const presets = {
    support: [
      { author: 'admin.north', text: 'Добро пожаловать. Здесь виден ритм внутренней поддержки после регистрации.' },
      { author: 'rovno.echo', text: 'Нужен быстрый старт и понимание, куда идти после входа.' },
      { author: 'admin.north', text: 'Смотри карточки справа: там актуальные handles, bot и резервная комната.' }
    ],
    contacts: [
      { author: 'support.bot', text: 'Telegram bot отвечает на стартовые вопросы и помогает не потеряться в первых шагах.' },
      { author: 'quiet.room', text: 'Element room оставлен как тихий резервный канал с отдельным потоком.' },
      { author: 'admin.north', text: 'Все контакты на этом экране демонстрационные и нужны для проектирования структуры.' }
    ],
    team: [
      { author: 'shift.lead', text: 'Для команды важны сменный ритм, спокойный текст и предсказуемый онлайн.' },
      { author: 'rovno.echo', text: 'Где посмотреть роли и условия?' },
      { author: 'shift.lead', text: 'Страница Команда держит роли, условия и воронку заявки в одном визуальном языке.' }
    ]
  };

  function renderMessages(name) {
    if (!(roomFeed instanceof HTMLElement)) {
      return;
    }

    const messages = presets[name] || presets.support;
    roomFeed.innerHTML = '';

    messages.forEach(function (message, index) {
      const article = document.createElement('article');
      article.className = 'message' + (index % 2 === 1 ? ' me' : '');

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