---
description: "Use when editing AI customization files in .github/: agents, skills, prompts, hooks, instructions, or copilot policy. Keep neighboring discovery surfaces in sync so routing, descriptions, and invocation hints do not drift apart."
applyTo: ".github/**"
---

# Синхронизация AI-кастомизаций

Эта инструкция применяется к workspace-level AI-кастомизациям в `.github/`.

## Что считается AI-кастомизацией

- `agents/*.agent.md`
- `skills/*/SKILL.md`
- `prompts/*.prompt.md`
- `hooks/*.json`
- `instructions/*.instructions.md`
- `copilot-instructions.md`

## Правило синхронизации

Если изменение влияет на то, как AI-контур обнаруживается, маршрутизируется или вызывается, не правь один файл изолированно. В том же change-set проверь и синхронизируй соседние discovery surfaces:

- `description`
- `argument-hint`
- разделы `КОГДА использовать / НЕ использовать`
- role/handoff policy в `copilot-instructions.md`
- соседние instruction/skill/prompt references
- связанные operator-docs touchpoints: запись в `todo`, а если меняется способ сопровождения AI-контура — и краткий блок в `README.md`

## Минимальный чек перед завершением

1. Проверить, что новый wording не конфликтует с root-agent role matrix.
2. Проверить, что trigger-слова не дублируют соседний агент, skill или prompt без причины.
3. Проверить, что `applyTo` остаётся узким и не превращается в глобальный контекст.
4. Проверить, что выбран правильный primitive: agent vs skill vs prompt vs instruction vs hook.
5. Закрыть change-set повторяемым smoke-check через `smoke-ai-customizations` по реально затронутым поверхностям.

## Чего не делать

- Не использовать `applyTo: "**"` для AI-кастомизаций.
- Не добавлять prompt, если нужен reusable workflow-level skill.
- Не добавлять skill, если нужен single-entry operator command.
- Не менять tool surface агентов в рамках чисто policy/instruction правки, если это не отдельная задача.