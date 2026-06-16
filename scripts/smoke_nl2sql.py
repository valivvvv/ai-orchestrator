"""
Smoke test for the NL2SQL agent.

Runs the full graph (generate -> validate -> execute, with the retry loop)
against the live achizitii_directe table and checks we get rows back.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))

from dotenv import load_dotenv
load_dotenv()

from nl2sql_agent import NL2SQLAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")

SCHEMA_PATH = str(Path(__file__).parent.parent / "data" / "nl2sql_agent" / "schema_achizitii_directe.json")


def main() -> int:
    agent = NL2SQLAgent(table_name="achizitii_directe", schema_path=SCHEMA_PATH)

    question = "Care sunt primele 5 contracte după valoarea în RON?"
    print(f"\n=== QUESTION: {question} ===")
    result = agent.run(question)

    status = result["status"]
    dataframe = result["result"]
    print(f"\nstatus      : {status}")
    print(f"sql_query   : {result['sql_query']}")
    print(f"retry_count : {result['retry_count']}")
    print(f"rows        : {len(dataframe)}")
    if not dataframe.empty:
        print(dataframe.to_string(index=False))

    if status != "success":
        print("\nFAIL: expected status=success")
        return 1
    if dataframe.empty:
        print("\nFAIL: expected a non-empty result set")
        return 1

    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
