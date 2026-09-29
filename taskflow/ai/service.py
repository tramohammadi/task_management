import json
import re
from django.conf import settings


# ---------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------
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


def build_goal_breakdown_prompt(user_goal):
    return f"""
You are an expert agile task manager assistant.
The user wants to accomplish the following goal or plan:
"{user_goal}"

Break down this goal into 3 to 6 practical, actionable, and concise tasks.
Strict rules:
- Always respond in English, regardless of the input language.
- Keep task titles short, crisp, and imperative (e.g., "Design Database Schema", max 50 chars).
- Provide a brief 1-sentence description explaining the task.
- Set priority strictly to one of: LOW, MEDIUM, HIGH.
- Return ONLY a valid JSON array of objects. Do not include markdown codeblocks, backticks, or extra text.

Example format:
[
  {{"title": "Design Database Schema", "description": "Define models and relationships for users, products, and orders", "priority": "HIGH"}},
  {{"title": "Implement User Authentication", "description": "Set up registration, login, and session handling", "priority": "HIGH"}}
]
"""


def build_project_summary_prompt(context_data):
    return f"""
You are a professional project management consultant.

Based on the following project data, write a concise and useful project summary.
Include: current status, key risks, and suggested next steps.

PROJECT DATA:
{context_data}

Return plain text (not JSON).
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



def _call_openai_compatible(prompt, system_message):
    """Calls AvalAI or OpenAI depending on AI_PROVIDER."""
    from openai import OpenAI

    provider = getattr(settings, "AI_PROVIDER", "avalai").lower()

    if provider == "avalai":
        api_key = getattr(settings, "AVALAI_API_KEY", None)
        base_url = "https://api.avalai.ir/v1"
    elif provider == "openai":
        api_key = getattr(settings, "OPENAI_API_KEY", None)
        base_url = None
    else:
        raise ValueError(f"Unsupported provider for OpenAI client: {provider}")

    if not api_key:
        raise ValueError(f"{provider.upper()}_API_KEY is not configured.")

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


def _call_gemini(prompt):
    import google.generativeai as genai

    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text


def _call_llm(prompt, system_message):
    """Dispatches to the configured provider."""
    provider = getattr(settings, "AI_PROVIDER", "avalai").lower()
    if provider in ("avalai", "openai"):
        return _call_openai_compatible(prompt, system_message)
    elif provider == "gemini":
        return _call_gemini(prompt)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")


def generate_task_suggestions(project_description):
    prompt = build_task_prompt(project_description)
    content = _call_llm(
        prompt,
        "You are a helpful software project management assistant that outputs only raw JSON.",
    )
    return clean_suggestions(content)


def generate_goal_breakdown(user_goal):
    prompt = build_goal_breakdown_prompt(user_goal)
    content = _call_llm(
        prompt,
        "You are a helpful project task planner that only responds with raw JSON.",
    )
    return clean_suggestions(content)


def generate_project_summary(context_data):
    prompt = build_project_summary_prompt(context_data)
    content = _call_llm(
        prompt,
        "You are a professional project management consultant.",
    )
    return content