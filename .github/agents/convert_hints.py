import json
import os
from pathlib import Path

def convert_to_markdown(json_path: Path) -> Path:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Создаем файл с тем же именем, но расширением .md
    # Если файл назывался xxx-hint.json, можно переименовать в xxx.md (опционально)
    md_path = json_path.with_suffix('.md')
    lines = []

    # 1. Заголовок и мета-информация
    name = data.get("name", json_path.stem).upper()
    lines.append(f"# {name} API Reference\n")

    if "description" in data:
        lines.append(f"{data['description']}\n")

    # 2. Copilot Prompts (Самое важное для LLM)
    prompts = data.get("copilot_prompt_lines", [])
    if prompts:
        lines.append("> ⚠️ **ВАЖНЫЕ ПРАВИЛА (TL;DR):**")
        for i, prompt in enumerate(prompts, 1):
            lines.append(f"> {i}. {prompt}")
        lines.append("")

    # 3. Привязка к проекту
    refs = data.get("project_references", {})
    if refs:
        lines.append("## Привязка к проекту")
        for key, val in refs.items():
            lines.append(f"- **{key}**: `{val}`")
        lines.append("")

    # 4. Справочник API (Reference)
    reference = data.get("reference", {})
    if reference:
        lines.append("## Справочник API (Reference)\n")
        for section, content in reference.items():
            if not content:
                continue
            lines.append(f"### {section.replace('_', ' ').title()}")
            for key, val in content.items():
                if section == "endpoints":
                    lines.append(f"- **{key}**: `{val}`")
                else:
                    lines.append(f"- **{key}**: {val}")
            lines.append("")

    # 5. Текущее состояние
    state = data.get("current_project_state", {})
    if state:
        lines.append("## Текущее состояние проекта\n")
        for section, items in state.items():
            if not items:
                continue
            lines.append(f"### {section.replace('_', ' ').title()}")
            for item in items:
                if section == "existing_env_vars":
                    lines.append(f"- `{item}`")
                else:
                    checkbox = "x" if section == "implemented" else " "
                    lines.append(f"- [{checkbox}] {item}")
            lines.append("")

    # 6. Правила реализации
    rules = data.get("implementation_rules", [])
    if rules:
        lines.append("## Правила реализации")
        for rule in rules:
            lines.append(f"- {rule}")
        lines.append("")

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    return md_path

def main():
    # Запуск предполагается из корня проекта (g:\CER24BER)
    api_dir = Path("doc/api")
    if not api_dir.exists():
        print(f"Директория {api_dir} не найдена.")
        return

    json_files = list(api_dir.rglob("*.json"))
    if not json_files:
        print("JSON файлы не найдены.")
        return

    for json_path in json_files:
        try:
            md_path = convert_to_markdown(json_path)
            print(f"Успешно сконвертировано: {json_path.name} -> {md_path.name}")
        except Exception as e:
            print(f"Ошибка при конвертации {json_path.name}: {e}")

if __name__ == "__main__":
    main()