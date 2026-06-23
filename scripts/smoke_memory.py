"""
Smoke test for conversation memory (Phase 1).

Runs a two-turn conversation on the same session_id against the Orchestrator,
showing that turn 2 is contextualized from turn-1 history and that turns
persist in PostgreSQL across process restarts.

Usage:
    python scripts/smoke_memory.py            # appends to the session (re-run shows growth)
    python scripts/smoke_memory.py --reset     # clear the session first
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from skillab import get_llm
from database import transaction
from models import ChatMessage, Session as SessionModel
from orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)

SESSION_ID = "smoke_memory_s1"


def show_rows(session_id: str) -> None:
    with transaction() as session:
        rows = (
            session.query(ChatMessage)
            .filter_by(session_id=session_id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
            .all()
        )
    print(f"\nchat_messages for {session_id!r}: {len(rows)} rows")
    for row in rows:
        print(f"  [{row.id}] {row.role}: {row.content[:80]}")


def reset(session_id: str) -> None:
    with transaction() as session:
        session.query(ChatMessage).filter_by(session_id=session_id).delete()
        session.query(SessionModel).filter_by(id=session_id).delete()


def main() -> None:
    if "--reset" in sys.argv:
        reset(SESSION_ID)
        print(f"Reset session {SESSION_ID!r}.")
    else:
        show_rows(SESSION_ID)  # rows surviving from a previous run (restart persistence)

    llm = get_llm(provider="anthropic")
    print(f"Using LLM: anthropic / {llm.model}")
    orchestrator = Orchestrator(llm=llm)

    print("\n" + "=" * 60)
    print("TURN 1")
    print("=" * 60)
    turn1 = orchestrator.run("Ce contact are DataPro?", session_id=SESSION_ID)
    print(f"Status: {turn1['status']}")
    print(f"Answer: {turn1['answer'][:300]}")

    print("\n" + "=" * 60)
    print("TURN 2 (follow-up - should be contextualized to DataPro)")
    print("=" * 60)
    turn2 = orchestrator.run("Și ce adresă are?", session_id=SESSION_ID)
    print(f"Status: {turn2['status']}")
    print(f"Answer: {turn2['answer'][:300]}")

    show_rows(SESSION_ID)
    print("\nRe-run this script to confirm persistence across restarts.")


if __name__ == "__main__":
    main()
