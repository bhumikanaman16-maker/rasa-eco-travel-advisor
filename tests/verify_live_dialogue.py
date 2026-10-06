import requests
import json
import time
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RASA_URL = "http://127.0.0.1:5005/webhooks/rest/webhook"

def send_msg(sender_id, text):
    resp = requests.post(
        RASA_URL,
        json={"sender": sender_id, "message": text},
        timeout=15
    )
    if resp.ok:
        return resp.json()
    print(f"Error HTTP {resp.status_code}: {resp.text}")
    return []

def run_test():
    sender_id = f"test_e2e_{int(time.time())}"
    print(f"=== Starting Multi-Turn Live Test (Session: {sender_id}) ===\n")

    steps = [
        ("User starts trip planning", "/plan_trip"),
        ("User provides destination", "Paris"),
        ("User provides duration", "5 days"),
        ("User provides dates", "10 October to 15 October"),
        ("User provides party", "Couple"),
        ("User provides style", "Nature & Wildlife"),
        ("User provides pace", "Balanced"),
        ("User provides budget", "1200 euros"),
        ("User provides sustainability", "high"),
        ("User requests custom itinerary", "/ask_itinerary"),
        ("User requests green dining", "/ask_dining"),
        ("User requests packing checklist", "/ask_packing_tips"),
        ("User requests eco travel tips", "/ask_eco_tips"),
        ("User asks for budget advice", "How should I divide my budget?"),
    ]

    for label, msg in steps:
        print(f"👉 [{label}]: {msg}")
        bot_replies = send_msg(sender_id, msg)
        for r in bot_replies:
            txt = r.get("text", "")
            buttons = r.get("buttons", [])
            print(f"🤖 Bot:\n{txt}\n")
            if buttons:
                btn_titles = [b['title'] for b in buttons]
                print(f"   [Buttons]: {btn_titles}\n")
        print("-" * 60)

if __name__ == "__main__":
    run_test()
