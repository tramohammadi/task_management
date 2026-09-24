import json
import re
from django.conf import settings


def build_task_prompt(project_description):
    return f"""
You are an assistant inside a project management application.

The user wants to create tasks for this project.

PROJECT DESCRIPTION:
{project_description}

Generate 3 to 7 practical and actionable initial tasks.

Rules:
- Tasks must be relevant to the project.
- Do not create duplicate tasks.
- Keep task titles short and clear.
- Give each task a useful description.
- Priority must be exactly one of: LOW, MEDIUM, HIGH
- Do not generate deadlines.
- Return ONLY valid JSON array. Do not include markdown formatting or backticks.
- Each object must contain exactly these fields: title, description, priority

Example:
[
    {{
        "title": "Design the database",
        "description": "Define the database models and relationships required by the project.",
        "priority": "HIGH"
    }},
    {{
        "title": "Implement authentication",
        "description": "Create registration, login and logout functionality.",
        "priority": "HIGH"
    }}
]
"""


def clean_suggestions(raw_text):
    if not raw_text:
        raise ValueError("AI response was empty.")

    cleaned_text = raw_text.strip()
    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
        cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
    cleaned_text = cleaned_text.strip()

    try:
        suggestions = json.loads(cleaned_text)
    except json.JSONDecodeError:
        raise ValueError(f"AI returned invalid JSON: {raw_text[:100]}")

    if not isinstance(suggestions, list):
        raise ValueError("AI response must be a list.")

    valid_priorities = {"LOW", "MEDIUM", "HIGH"}
    cleaned_suggestions = []

    for item in suggestions:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        priority = str(item.get("priority", "MEDIUM")).upper().strip()

        if not title:
            continue

        if priority not in valid_priorities:
            priority = "MEDIUM"

        cleaned_suggestions.append({
            "title": title[:255],
            "description": description,
            "priority": priority,
        })

    return cleaned_suggestions[:7]


# AvalAI
def generate_with_avalai(project_description):
    from openai import OpenAI

    api_key = getattr(settings, "AVALAI_API_KEY", None)
    if not api_key:
        raise ValueError("AVALAI_API_KEY is not configured.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.avalai.ir/v1"
    )

    prompt = build_task_prompt(project_description)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful software project management assistant that outputs only raw JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content
    return clean_suggestions(content)


def generate_with_openai(project_description):
    from openai import OpenAI

    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=api_key)
    prompt = build_task_prompt(project_description)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful software project management assistant that outputs only raw JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content
    return clean_suggestions(content)


def generate_with_gemini(project_description):
    import google.generativeai as genai

    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = build_task_prompt(project_description)
    response = model.generate_content(prompt)

    return clean_suggestions(response.text)


def generate_task_suggestions(project_description):
    provider = getattr(settings, "AI_PROVIDER", "avalai").lower()

    if provider == "avalai":
        return generate_with_avalai(project_description)
    elif provider == "openai":
        return generate_with_openai(project_description)
    elif provider == "gemini":
        return generate_with_gemini(project_description)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")