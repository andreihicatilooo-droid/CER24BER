---
name: "sync-ai-policy"
description: "Синхронизировать соседние AI discovery surfaces и docs touchpoints после правок в .github и policy-файлах."
argument-hint: "Укажи изменённые AI-файлы и что именно нужно выровнять"
agent: "CERBER"
---

Заведи запрос в узкий maintenance workflow для синхронизации AI-кастомизаций после правок.

Проверь соседние discovery surfaces, descriptions, argument-hint, role boundaries и policy/docs touchpoints только в пределах реального change-set.
Не расширяй scope на новые hooks, prompts, skills или agents без отдельной задачи. Если для sync нужен отдельный edit-slice, передай дальше только его, а финальный повторяемый check оставь `smoke-ai-customizations`.