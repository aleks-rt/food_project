import os
import anthropic
from datetime import date

MODEL = "claude-sonnet-4-6"

FORMAT_INSTRUCTIONS = """
Форматируй ответ для Telegram используя только эти теги:
- <b>текст</b> — жирный (для названий блюд и заголовков)
- <i>текст</i> — курсив (для пометок)
- Эмодзи для визуального разделения секций
- Простые списки через дефис или цифры (без markdown)
- НЕ используй ## ### ** __ и другой markdown
- Таблицы заменяй простым списком: "Имя — Xг"
"""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _build_family_context(user: dict, members: list[dict]) -> str:
    people = [f"- {user['name']}: {user['age']} лет, {user['weight']} кг, цель {user['calories']} ккал/день"]
    for m in members:
        people.append(f"- {m['name']}: {m['age']} лет, {m['weight']} кг, цель {m['calories']} ккал/день")
    return "\n".join(people)


def _build_restrictions(user: dict, exclusions: list[str]) -> str:
    parts = []
    if user.get("allergies"):
        parts.append(f"Аллергия: {', '.join(user['allergies'])}")
    if user.get("dislikes"):
        parts.append(f"Не любят: {', '.join(user['dislikes'])}")
    if exclusions:
        parts.append(f"Исключить сегодня (заменить чем-то): {', '.join(exclusions)}")
    return "\n".join(parts) if parts else "Нет ограничений"


async def generate_daily_recipes(user: dict, members: list[dict], exclusions: list[str]) -> str:
    family_ctx = _build_family_context(user, members)
    restrictions = _build_restrictions(user, exclusions)
    total_people = 1 + len(members)
    today = date.today().strftime("%d.%m.%Y")

    prompt = f"""Ты — диетолог и шеф-повар. Составь план питания на сегодня ({today}) для семьи.

Члены семьи:
{family_ctx}

Ограничения и пожелания:
{restrictions}

Задача:
1. Предложи 3 блюда (завтрак, обед, ужин).
2. Для каждого блюда дай подробный рецепт с ингредиентами и шагами.
3. Укажи граммовку для каждого члена семьи (всего {total_people} чел.) с учётом их калорийности.
4. Если исключены продукты — замени на аналоги и укажи чем заменено.
5. Для каждого приёма пищи укажи КБЖУ на порцию.

{FORMAT_INSTRUCTIONS}

Пример структуры одного приёма пищи:
🌅 <b>ЗАВТРАК: Название блюда</b>

🥘 <b>Ингредиенты:</b>
- Продукт 1
- Продукт 2

👨‍🍳 <b>Приготовление:</b>
1. Шаг первый
2. Шаг второй

⚖️ <b>Граммовка:</b>
Имя1 — продукт: Xг, продукт: Yг
Имя2 — продукт: Xг, продукт: Yг

📊 <b>КБЖУ на порцию:</b>
Имя1: Xккал | Б:Xг | Ж:Xг | У:Xг
Имя2: Xккал | Б:Xг | Ж:Xг | У:Xг
"""

    full_response = ""
    with _client().messages.stream(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            full_response += text

    return full_response


async def generate_fridge_recipes(
    user: dict, members: list[dict], exclusions: list[str], fridge_contents: str
) -> str:
    family_ctx = _build_family_context(user, members)
    restrictions = _build_restrictions(user, exclusions)
    total_people = 1 + len(members)

    prompt = f"""Ты — диетолог и шеф-повар. На основе продуктов из холодильника придумай блюда для семьи.

Члены семьи:
{family_ctx}

Что есть в холодильнике:
{fridge_contents}

Ограничения и пожелания:
{restrictions}

Задача:
1. Предложи 2–3 блюда из указанных продуктов (базовые специи, соль, масло — можно добавить).
2. Для каждого блюда дай рецепт с ингредиентами и шагами приготовления.
3. Укажи граммовку для каждого члена семьи (всего {total_people} чел.) с учётом их калорийности.
4. Если исключены продукты — замени из того что есть или обойди без них.
5. Для каждого блюда укажи КБЖУ на порцию.

{FORMAT_INSTRUCTIONS}

Пример структуры одного блюда:
🍽 <b>Название блюда</b>

🥘 <b>Ингредиенты:</b>
- Продукт 1
- Продукт 2

👨‍🍳 <b>Приготовление:</b>
1. Шаг первый
2. Шаг второй

⚖️ <b>Граммовка:</b>
Имя1 — продукт: Xг, продукт: Yг
Имя2 — продукт: Xг, продукт: Yг

📊 <b>КБЖУ на порцию:</b>
Имя1: Xккал | Б:Xг | Ж:Xг | У:Xг
Имя2: Xккал | Б:Xг | Ж:Xг | У:Xг
"""

    full_response = ""
    with _client().messages.stream(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            full_response += text

    return full_response
