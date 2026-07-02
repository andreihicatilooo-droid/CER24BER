---
name: smoke-ai-customizations
description: "Провести repeatable smoke-check AI-кастомизаций по сценариям и файлам после правок в `.github/`. Используй, когда нужно проверить frontmatter, discovery visibility, role boundaries и базовые handoff-сценарии без превращения проверки в новый агент или hook."
argument-hint: "Укажи изменённые AI-файлы и, если нужно, сценарии для smoke-check"
---

# smoke-ai-customizations

Даёт короткий и повторяемый close-out smoke-check для AI-кастомизаций: какие файлы смотрим, какие сценарии прогоняем и что считается pass/fail перед закрытием change-set.

## Когда использовать

- После правок в agents, skills, prompts, hooks, instructions или `.github/copilot-instructions.md`
- Перед закрытием задачи по AI-контуру, когда нужен repeatable check по конкретным файлам и сценариям
- Когда нужно быстро убедиться, что frontmatter, discovery visibility и handoff-границы остались согласованными

## Когда не использовать

- Не для внесения правок и синхронизации wording: это `sync-ai-contour`
- Не для ideation или выбора следующего агента: это зона **CERBER**, **CERBER Router** и `idea-to-brief`
- Не для немедленной записи уже сформированного TODO-ready списка задач: этим владеет `CERBER TODO`, который при необходимости использует `plan-to-todo`
- Не для автоматического enforcement: если нужен обязательный запуск, это отдельная задача про hooks или CI
- Не придумывай отсутствующие prompts/hooks ради проверки: помечай такие поверхности как `N/A`

## Роль в AI-контуре

- Это reusable verification skill, а не новый агент
- Он не принимает routing-решения за **CERBER Router** и не подменяет planning-работу **CERBER Planner**
- Его задача одна: повторяемо проверить уже изменённый AI-контур по файлам, docs touchpoints и сценариям

## Процедура

### Шаг 0 — Определить scope проверки

Собери список реально изменённых AI-файлов и зафиксируй, какие поверхности существуют в текущем шаге:

- `agents/*.agent.md`
- `skills/*/SKILL.md`
- `prompts/*.prompt.md`
- `hooks/*.json`
- `instructions/*.md`
- `.github/copilot-instructions.md`
- `README.md`, если change-set меняет contributor-facing вход в AI contour maintenance
- `todo`, если задача ведётся через TODO-цепочку

Если prompts или hooks ещё не введены, не расширяй scope: просто отметь их как `N/A`.

### Шаг 1 — Проверить файлы

Для каждого файла в scope проверь:

- корректен ли frontmatter (`name`, `description`, `argument-hint`, если файл его использует);
- совпадает ли имя skill с именем папки;
- нет ли явного конфликта wording с соседним agent, skill или prompt;
- не обещает ли файл поведение, которого в этом шаге ещё нет.

Отдельно пройди file surfaces/checklist:

- prompts остаются thin entry points и не дублируют тело skills;
- hooks остаются guard/reminder-слоем и не перетягивают на себя sync/smoke workflow;
- `README.md` и `todo` не расходятся с текущим способом сопровождения AI-контура, если они входят в scope;
- если нашёл wording drift, фиксируй это как `FAIL` для smoke-check и отправляй на `sync-ai-contour`, а не расширяй проверку в новый edit-slice.

### Шаг 2 — Прогнать минимальные сценарии

Минимальный набор сценариев:

1. Запрос на сырую идею должен вести к `idea-to-brief`, а не к policy-maintenance skill.
2. Запрос на немедленную запись уже сформированного списка задач в TODO должен вести к `CERBER TODO`, который при необходимости использует `plan-to-todo`.
3. Запрос на синхронизацию AI-кастомизаций после правок должен вести к `sync-ai-contour`.
4. Запрос на повторяемую проверку AI-кастомизаций по файлам и сценариям должен вести к `smoke-ai-customizations`.
5. Если в change-set был contributor-facing docs/policy touchpoint, smoke-check должен подтверждать тот же workflow в `README.md`, `todo` и `.github`-поверхностях без нового расхождения ролей.

Если сценарий не покрывается текущим change-set'ом, честно пометь это как gap, а не достраивай соседний контур заранее.

### Шаг 3 — Зафиксировать pass/fail

В отчёте перечисли:

- что прошло;
- что не прошло;
- что было `N/A`;
- какой один следующий фикс нужен, если есть конфликт discovery.

Критерии:

- `PASS` — frontmatter валиден, naming и wording согласованы, prompts/hooks не вышли за свою роль, а все затронутые docs touchpoints подтверждают тот же workflow;
- `FAIL` — есть конфликт role boundaries, broken frontmatter, несогласованный prompt/skill/hook wording или расходящийся README/todo touchpoint;
- `N/A` — поверхность отсутствует в текущем scope и не должна достраиваться ради проверки.

## Формат ответа

```markdown
Smoke-check:
- Scope: <какие файлы проверялись>
- File surfaces: <что именно проверялось по чеклисту>
- Pass: <что прошло>
- Fail: <что сломано, если есть>
- N/A: <какие поверхности отсутствуют на этом шаге>
- Итог: PASS / FAIL

Сценарии:
1. <сценарий> — PASS / FAIL
2. <сценарий> — PASS / FAIL

Следующий фикс:
- <только если реально нужен>
```