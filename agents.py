import re
import time
import json
import requests
from system_prompts import CEO_SYSTEM, CODER_SYSTEM, TESTER_SYSTEM
from config import OPENROUTER_MODEL, OPENROUTER_API_KEY, TOOLS_SCHEMA
from logger import log
from database import save_message, get_messages
from tools import dispatch_tool


def llm_call(messages: list[dict], system: str = "") -> str:
    import time

    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": all_messages,
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=300,
            )
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                log("ERR", f"Rate limit 429, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(4)
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log("ERR", f"llm_call failed: {e}")
            if attempt < 2:
                time.sleep(10)

    return "LLM ERROR: rate limit or timeout"

def llm_with_tools(
    agent_name: str,
    system: str,
    user_prompt: str,
    sprint: int = 0,
    max_tool_calls: int = 5,
) -> str:
    tool_desc = json.dumps(TOOLS_SCHEMA, indent=2, ensure_ascii=False)

    full_system = f"""{system}

You have access to the following tools. To call a tool, respond ONLY with this JSON format (nothing else):
{{"tool_call": true, "tool": "<name>", "args": {{...}}}}

If you don't need a tool, respond normally as text.

Available tools:
{tool_desc}
"""
    history = get_messages(agent_name) if agent_name != "coder" else []
    history.append({"role": "user", "content": user_prompt})
    save_message("user", agent_name, user_prompt, sprint)

    for _ in range(max_tool_calls):
        time.sleep(4)
        response = llm_call(history, full_system)

        try:
            json_match = re.search(r'\{.*"tool_call".*\}', response, re.DOTALL)
            if json_match:
                call = json.loads(json_match.group())
                if call.get("tool_call"):
                    tool_name = call["tool"]
                    tool_args = call.get("args", {})
                    log(
                        agent_name.upper()[:5],
                        f"🔧 tool_call: {tool_name}({tool_args})",
                    )

                    tool_result = dispatch_tool(tool_name, tool_args)
                    tool_result_str = (
                        json.dumps(tool_result, ensure_ascii=False)
                        if not isinstance(tool_result, str)
                        else tool_result
                    )

                    history.append({"role": "assistant", "content": response})
                    history.append(
                        {
                            "role": "user",
                            "content": f"[TOOL RESULT - {tool_name}]\n{tool_result_str}",
                        }
                    )
                    save_message("assistant", agent_name, response, sprint)
                    save_message(
                        "user",
                        agent_name,
                        f"[TOOL RESULT - {tool_name}]\n{tool_result_str}",
                        sprint,
                    )
                    continue
        except (json.JSONDecodeError, AttributeError):
            pass

        save_message("assistant", agent_name, response, sprint)
        return response

    save_message("assistant", agent_name, response, sprint)
    return response


def ceo_action(prompt: str, sprint: int = 0) -> str:
    log("CEO", f"💭 {prompt[:80]}...")
    return llm_with_tools("ceo", CEO_SYSTEM, prompt, sprint)


def coder_action(prompt: str, sprint: int = 0) -> str:
    log("CODER", f"💻 {prompt[:80]}...")
    return llm_with_tools("coder", CODER_SYSTEM, prompt, sprint)


def tester_action(prompt: str, sprint: int = 0) -> str:
    log("TEST", f"🧪 {prompt[:80]}...")
    return llm_with_tools("tester", TESTER_SYSTEM, prompt, sprint, max_tool_calls=8)