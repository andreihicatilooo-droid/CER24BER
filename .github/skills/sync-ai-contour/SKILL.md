---
name: sync-ai-contour
description: "Синхронизировать соседние discovery surfaces после правки agents, skills, prompts, hooks, instructions или copilot policy. Используй, когда нужно выровнять descriptions, argument-hint, role boundaries и policy touchpoints, чтобы AI-контур не расходился по файлам."
argument-hint: "Укажи, какие AI-кастомизации менялись и что нужно синхронизировать"
---

# sync-ai-contour

Сводит точечные правки AI-кастомизаций к одному аккуратному sync-проходу: какие поверхности изменились, что нужно выровнять рядом и что сознательно не трогаем до финального smoke-check.

## Когда использовать

- После правок в `.github/agents/`, `.github/skills/`, `.github/prompts/`, `.github/hooks/`, `.github/instructions/` или `.github/copilot-instructions.md`
- Когда изменились `description`, `argument-hint`, role boundaries, handoff notes или policy wording
- Когда нужно быстро проверить, что discovery и routing не расходятся между соседними файлами

## Когда не использовать

- Не для user-facing маршрутизации: запрос пользователя по-прежнему ведут **CERBER**, **CERBER Router** или профильный агент
- Не для ideation-flow: сырые идеи ведёт `idea-to-brief`
- Не для переноса уже сформированного TODO-ready списка задач в TODO: этим владеет `CERBER TODO`, который при необходимости использует `plan-to-todo`
- Не для повторяемой проверки сценариев после правок: это `smoke-ai-customizations`
- Не для single-entry operator command: если нужен отдельный slash-command, это уже prompt, а не этот skill
- Не для финального закрытия change-set: после синхронизации остаётся отдельный repeatable smoke-check через `smoke-ai-customizations`

## Роль в AI-контуре

- Это reusable maintenance skill, а не новый агент
- Он не подменяет **CERBER**, **CERBER Router** или **CERBER Planner** и не принимает на себя их decision-making
- Его задача узкая: после правок AI-контура синхронизировать соседние discovery surfaces минимальным change-set'ом

## Процедура

### Шаг 0 — Зафиксировать change-set

Собери только те AI-файлы, которые реально менялись, и ближайшие surfaces, которые они затрагивают:

- `description`
- `argument-hint`
- секции "Когда использовать / Когда не использовать"
- role/handoff policy в `.github/copilot-instructions.md`
- связанные записи в `todo`, если задача ведётся через AI-контур
- краткий блок в `README.md`, если change-set меняет contributor-facing способ сопровождения AI-контура

Не расширяй scope на несвязанные prompts, hooks или agents "на всякий случай".

### Шаг 1 — Проверить соседние поверхности

Для каждого изменённого файла проверь:

- не появилось ли дублирование trigger-слов с соседним агентом, skill или prompt;
- совпадает ли узкая роль файла с root-agent role matrix;
- не разошлись ли `description`, `argument-hint` и body по смыслу;
- не требует ли change-set явного policy touchpoint в `.github/copilot-instructions.md`.

### Шаг 2 — Синхронизировать минимально

- Обновляй только те соседние surfaces, которые реально разошлись
- Не превращай skill в agent и не добавляй prompts/hooks заранее
- Если старый wording всё ещё корректен, оставляй его без косметических правок
- Если изменение влияет на AI-контур, синхронизируй policy и docs/task touchpoints в том же change-set
- Если после синхронизации остаётся вопрос только проверки, не продолжай правки здесь: передай закрывающий проход в `smoke-ai-customizations`

### Шаг 3 — Кратко зафиксировать результат

В конце перечисли:

- какие файлы синхронизированы;
- какие surfaces проверены;
- какие touchpoints нужно закрыть повторяемым smoke-check;
- что сознательно не менялось, чтобы scope не расползался.

## Формат ответа

```markdown
Синхронизировано:
- <файл или поверхность>
- <файл или поверхность>

Проверено:
- description / argument-hint / role boundaries / policy touchpoints
- <если было: todo / README touchpoint>

Дальше проверить:
- <что должен подтвердить `smoke-ai-customizations`>

Не трогал:
- <что сознательно оставлено вне scope>

Риск:
- <если осталась неоднозначность, назвать её одной строкой>
```