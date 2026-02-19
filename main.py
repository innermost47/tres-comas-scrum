import os
import json
import time
from agents import (
    ceo_action,
    coder_action,
    tester_action
)
from config import MAX_CODER_ATTEMPTS, SPRINT_SIZE
from helpers import apply_delivery, run_delivery_tests, extract_key_error, extract_delivery, extract_json
from tools import tool_list_files, tool_read_file, tool_list_files
from database import init_db, load_state, save_state
from logger import log

def process_ticket(ticket: dict, sprint_num: int) -> bool:
    ticket_id = ticket["id"]
    log("CEO", f"📋 Processing ticket {ticket_id}: {ticket['title']}")

    existing_files = tool_list_files()
    existing_code = ""
    for filepath in existing_files.split("\n"):
        if filepath.strip():
            content = tool_read_file(filepath.replace("output/", ""))
            existing_code += f"\n### {filepath}\n```python\n{content}\n```\n"

        coder_prompt = f"""Ticket to implement:
ID: {ticket_id}
Title: {ticket['title']}
Description: {ticket['description']}
Acceptance criteria: {json.dumps(ticket.get('acceptance_criteria', []))}

EXISTING CODEBASE (don't overwrite, extend only):
{existing_code}

Produce only new or modified files.
IMPORTANT: In your test files, NEVER import from framework/ or local modules."""

    error_context = ""

    for attempt in range(1, MAX_CODER_ATTEMPTS + 1):
        log("CODER", f"🔄 Attempt {attempt}/{MAX_CODER_ATTEMPTS} for {ticket_id}")

        prompt = coder_prompt
        if error_context:
            prompt += (
                f"\n\n⚠️ ERRORS to fix (previous attempt):\n{error_context}"
            )

        response = coder_action(prompt, sprint_num)
        delivery = extract_delivery(response)
        print(response)

        if not delivery or not delivery.get("files"):
            log("ERR", f"Empty delivery or no files!")
            error_context = "You delivered no files. You MUST deliver code in <file> tags."
            continue 

        if not delivery or delivery.get("type") != "code_delivery":
            log("ERR", f"Invalid Coder response for {ticket_id}")
            error_context = f"Your response was not in the expected XML <delivery> format. Response received: {response[:500]}"
            continue

        log("CODER", f"📦 Delivery received: {len(delivery.get('files', []))} file(s)")

        test_result = run_delivery_tests(delivery)

        if test_result["success"]:
            log("CODER", f"✅ Tests OK for {ticket_id}")
            apply_delivery(delivery)
            return True
        else:
            log("ERR", f"❌ Tests KO for {ticket_id} (attempt {attempt})")
            key_error = extract_key_error(test_result['stderr'])
            error_context = f"""PRECISE ERROR to fix:
{key_error}

INSTRUCTION: Fix ONLY the error above.
- If it's a missing module → add it ONLY in <requirements>, don't touch the code
- If it's an error on a line → fix ONLY that line in the file concerned
- Rewrite the complete file ONLY if the fix touches multiple places
"""
            log("ERR", f"stderr: {test_result['stderr']}")

    log("ERR", f"💀 {ticket_id} failed after {MAX_CODER_ATTEMPTS} attempts")
    return False


def run_sprint(sprint_num: int, tickets: list) -> dict:
    log("CEO", f"🏃 Start Sprint {sprint_num} - {len(tickets)} tickets")
    results = {"approved": [], "rejected": []}

    for ticket in tickets:
        success = process_ticket(ticket, sprint_num)
        if success:
            results["approved"].append(ticket["id"])
        else:
            results["rejected"].append(ticket["id"])

    log(
        "CEO",
        f"📊 Sprint {sprint_num} completed - ✅ {len(results['approved'])} / ❌ {len(results['rejected'])}",
    )
    return results


def run_tester(sprint_num: int) -> list:
    files = tool_list_files()
    if not files or files == "No files.":
        log("TEST", "⏭️  No code to test yet")
        return []

    log("TEST", "🧪 The Tester is inspecting the framework...")
    response = tester_action(
        f"""The agentic framework evolved during sprint {sprint_num}.
Here are the available files:
{files}

Explore the code with read_file, try to use it with exec_code.
Tell me what you think as a user: what works, what's missing, what frustrated you.
Propose concrete user stories based on your real frustrations.""",
        sprint=sprint_num,
    )
    log("TEST", f"Raw tester response: {response[:500]}")
    data = extract_json(response)
    if data and data.get("type") == "tester_feedback":
        log("TEST", f"📣 Overall verdict: {data.get('overall', '?')}")
        for w in data.get("what_works", []):
            log("TEST", f"  ✅ {w}")
        for f in data.get("frustrations", []):
            log("TEST", f"  😤 {f}")
        for m in data.get("what_is_missing", []):
            log("TEST", f"  ❓ {m}")
        return data.get("suggested_stories", [])

    log("TEST", "⚠️  Tester feedback not parseable")
    return []


def main():
    log("WATCH", "🚀 Starting autonomous agentic system")
    init_db()
    os.makedirs("output", exist_ok=True)

    sprint_num = load_state("sprint_num", 1)
    backlog = load_state("backlog", [])
    done = load_state("done", [])

    if not backlog:
        log("CEO", "🎯 Generating initial backlog...")
        response = ceo_action(
            """Generate the initial backlog to build a minimalist Python agentic framework.
The framework will allow creating LLM agents with tools, memory and inter-agent communication.
Start with the foundations: basic structure, message system, first functional agent.
Generate 6 to 8 prioritized user stories (priority 1 = most important).""",
            sprint=0,
        )
        data = extract_json(response)
        if data and data.get("type") == "backlog":
            backlog = data["items"]
            save_state("backlog", backlog)
            log("CEO", f"📝 Backlog created: {len(backlog)} user stories")
            for us in backlog:
                log("CEO", f"  [{us['priority']}] {us['id']}: {us['title']}")
        else:
            log(
                "ERR",
                "Unable to parse initial backlog, will retry on next launch",
            )
            return

    while True:
        log("CEO", f"\n{'='*50}")
        log("CEO", f"📅 SPRINT {sprint_num} - Remaining backlog: {len(backlog)} tickets")
        log("CEO", f"{'='*50}")

        if not backlog:
            log(
                "CEO", "🎉 Empty backlog! The Tester is reviewing the entire framework..."
            )
            tester_stories = run_tester(sprint_num)
            if tester_stories:
                for s in tester_stories:
                    s.setdefault("id", f"TS-{sprint_num}-{tester_stories.index(s)+1}")
                    s.setdefault("priority", 2)
                    s.setdefault("acceptance_criteria", [])
                backlog.extend(tester_stories)
                save_state("backlog", backlog)
                log("CEO", f"📝 {len(tester_stories)} new stories from Tester")
            else:
                log("CEO", "⏸️  No new stories, pause 60s...")
                time.sleep(60)
            continue

        sorted_backlog = sorted(backlog, key=lambda x: x.get("priority", 99))
        sprint_tickets = sorted_backlog[:SPRINT_SIZE]

        log("CEO", f"📋 Planning Sprint {sprint_num}:")
        for t in sprint_tickets:
            log("CEO", f"  → {t['id']}: {t['title']}")

        sprint_results = run_sprint(sprint_num, sprint_tickets)

        approved_ids = set(sprint_results["approved"])
        done.extend([t for t in sprint_tickets if t["id"] in approved_ids])
        backlog = [
            t for t in backlog if t["id"] not in {x["id"] for x in sprint_tickets}
        ]

        for ticket in sprint_tickets:
            if ticket["id"] not in approved_ids:
                ticket["priority"] = 99
                backlog.append(ticket)

        save_state("backlog", backlog)
        save_state("done", done)
        save_state("sprint_num", sprint_num + 1)

        if sprint_num % 4 == 0:
            tester_stories = run_tester(sprint_num)
            if tester_stories:
                for s in tester_stories:
                    s.setdefault("id", f"TS-{sprint_num}-{tester_stories.index(s)+1}")
                    s.setdefault("priority", 3)
                    s.setdefault("acceptance_criteria", [])
                backlog.extend(tester_stories)
                save_state("backlog", backlog)
                log(
                    "CEO",
                    f"📝 {len(tester_stories)} stories from Tester added to backlog",
                )

        log("CEO", f"🔍 Sprint {sprint_num} Review...")
        review_response = ceo_action(
            f"""Sprint {sprint_num} completed.
Approved: {sprint_results['approved']}
Rejected: {sprint_results['rejected']}
Files in codebase: {tool_list_files()}
Remaining backlog: {len(backlog)} tickets
Do the sprint review. If you want to inspect code, use read_file.
Generate new user stories if you identify gaps.
Format: {{"type": "review", "approved": [...], "rejected": [...], "new_stories": [...], "framework_complete": false, "completion_reason": ""}}""",
            sprint=sprint_num,
        )
        review_data = extract_json(review_response)
        if review_data and review_data.get("new_stories"):
            new_stories = review_data["new_stories"]
            backlog.extend(new_stories)
            save_state("backlog", backlog)
            log("CEO", f"📝 {len(new_stories)} new user stories after CEO review")
        if review_data and review_data.get("framework_complete"):
            log("CEO", f"🏁 Framework complete: {review_data.get('completion_reason', '')}")
            break
        sprint_num += 1
        save_state("sprint_num", sprint_num)
        log("CEO", f"😴 Pause 5s before next sprint...")
        time.sleep(5)


if __name__ == "__main__":
    main()