"""
Run the full pipeline (Stages 1-6) on one or more companies from the
command line, and print what happened at each step.

This is a lightweight alternative to the Streamlit dashboard (app.py) -
useful for quickly testing your API keys and seeing raw output, without
opening a browser.

Run it with:
    python try_pipeline.py
"""

from database.database import initialize_database
from pipeline.lead_pipeline import process_one_company

# Edit this list to try different companies.
COMPANIES_TO_TRY = [
    "Honeywell",
    "Rockwell Automation",
]


if __name__ == "__main__":
    initialize_database()

    for company_name in COMPANIES_TO_TRY:
        print(f"\n=== {company_name} ===")
        result = process_one_company(company_name)

        for stage_name, stage_status in result["stages"].items():
            print(f"  {stage_name}: {stage_status}")

        if "error" in result:
            print(f"  UNEXPECTED ERROR: {result['error']}")

    print("\nDone. Run 'streamlit run app.py' to review results in the dashboard.")
