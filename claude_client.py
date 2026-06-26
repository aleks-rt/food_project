import anthropic
from datetime import date

client = anthropic.Anthropic()
MODEL = "claude-opus-4-8"


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
2. Для каждого блюда дай подробный рецепт с ингредиентами.
3. Укажи граммовку ОТДЕЛЬНО для каждого члена семьи (всего {total_people} чел.) с учётом их калорийности.
4. Если сегодня исключены какие-то продукты — обязательно замени их на подходящие аналоги и укажи чем заменено.
5. Для каждого приёма пищи укажи КБЖУ (калории, белки, жиры, углеводы) на порцию.
6. Отвечай на русском языке, структурированно и понятно.
"""

    full_response = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
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
1. Предложи 2–3 блюда, которые можно приготовить из указанных продуктов (можно добавить базовые специи, соль, масло).
2. Для каждого блюда дай подробный рецепт с ингредиентами и шагами приготовления.
3. Укажи граммовку ОТДЕЛЬНО для каждого члена семьи (всего {total_people} чел.) с учётом их калорийности.
4. Если исключены продукты — предложи замену из того, что есть в холодильнике или обойди без них.
5. Для каждого блюда укажи КБЖУ на порцию.
6. Отвечай на русском языке, структурированно и понятно.
"""

    full_response = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            full_response += text

    return full_response
