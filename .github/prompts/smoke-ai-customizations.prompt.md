---
name: "smoke-ai-customizations"
description: "Прогнать repeatable close-out smoke-check по AI-файлам, сценариям и затронутым docs touchpoints после правок."
argument-hint: "Укажи AI-файлы и, если нужно, сценарии для smoke-check"
agent: "CERBER"
---

Запусти только repeatable smoke-check для указанных AI-кастомизаций.

Проверь frontmatter, discovery visibility, role boundaries, docs touchpoints и базовые handoff-сценарии по текущему scope.
Отмечай отсутствующие поверхности как N/A и не превращай проверку в новый hook, рефакторинг или серию несвязанных правок. Если нашёл wording drift, фикс нужен через `sync-ai-contour`, а не внутри smoke-check.