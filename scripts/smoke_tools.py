"""
Smoke test for the analyst worker tools (join_data, filter_data).

Builds two small DataFrames, joins them via the registry, then filters the
joined result on a NUMERIC column using a STRING value ("100") — proving the
str->dtype cast in filter_data works (a numeric comparison against a raw
string would otherwise raise or silently match nothing).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))

import pandas

from skillab.tools import ToolWrapper


def main() -> int:
    employees = pandas.DataFrame(
        {
            "emp_id": [10, 11, 12, 13],
            "name": ["Ana", "Bob", "Cyn", "Dan"],
            "dept_id": [1, 2, 2, 3],
        }
    )
    departments = pandas.DataFrame(
        {
            "dept_id": [1, 2, 3],
            "dept_name": ["Eng", "Sales", "HR"],
            "budget": [50, 150, 300],
        }
    )

    print("\n=== join_data (inner on dept_id) ===")
    joined = ToolWrapper.call(
        "join_data",
        {
            "input_dfs": [employees, departments],
            "left_key": "dept_id",
            "right_key": "dept_id",
            "how": "inner",
        },
    )
    print(joined.to_string(index=False))
    print(f"joined rows : {len(joined)}")

    print("\n=== filter_data (budget > '100', string value vs numeric column) ===")
    filtered = ToolWrapper.call(
        "filter_data",
        {
            "input_dfs": [joined],
            "column": "budget",
            "operator": ">",
            "value": "100",
        },
    )
    print(filtered.to_string(index=False))
    print(f"filtered rows : {len(filtered)}")

    if len(joined) != 4:
        print("\nFAIL: expected 4 joined rows")
        return 1
    if len(filtered) != 3:
        print("\nFAIL: expected 3 rows with budget > 100 (Sales x2, HR x1)")
        return 1

    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
