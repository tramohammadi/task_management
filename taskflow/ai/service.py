import json

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
- Priority must be exactly one of:
  LOW, MEDIUM, HIGH
- Do not generate deadlines.
- Return ONLY valid JSON.
- Return a JSON array.
- Each object must contain exactly these fields:
  title
  description
  priority

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
    try:
        suggestions = json.loads(raw_text)

    except json.JSONDecodeError:
        raise ValueError("AI returned invalid JSON.")

    if not isinstance(suggestions, list):
        raise ValueError("AI response must be a list.")

    valid_priorities = {
        "LOW",
        "MEDIUM",
        "HIGH",
    }

    cleaned_suggestions = []

    for item in suggestions:

        if not isinstance(item, dict):
            continue

        title = str(
            item.get("title", "")
        ).strip()

        description = str(
            item.get("description", "")
        ).strip()

        priority = str(
            item.get("priority", "MEDIUM")
        ).upper().strip()

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


# OpenAI
def generate_with_openai(project_description):

    from openai import OpenAI

    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is not configured."
        )

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY
    )

    prompt = build_task_prompt(
        project_description
    )

    response = client.responses.create(
        model="gpt-5",
        input=prompt,
    )

    return clean_suggestions(
        response.output_text
    )

# Gemini

def generate_with_gemini(project_description):

    from google import genai

    if not settings.GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not configured."
        )

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY
    )

    prompt = build_task_prompt(
        project_description
    )

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )

    return clean_suggestions(
        response.text
    )


def generate_task_suggestions(project_description):

    provider = getattr(
        settings,
        "AI_PROVIDER",
        "openai"
    ).lower()

    if provider == "openai":

        return generate_with_openai(
            project_description
        )

    elif provider == "gemini":

        return generate_with_gemini(
            project_description
        )

    else:

        raise ValueError(
            f"Unsupported AI provider: {provider}"
        )