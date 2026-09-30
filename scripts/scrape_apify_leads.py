#!/usr/bin/env python3
"""
Scrape leads using Apify's code_crafter/leads-finder actor.

This script handles the API call to Apify, monitors the actor run,
and saves results to a JSON file.

2026-08-15: `.call()` used to return a dict (run['id'], run['defaultDatasetId'])
on older apify-client versions. After a venv rebuild pulled the latest
apify-client (requirements.txt only pins >=1.7.0, no upper bound), `.call()`
now returns a typed `apify_client._models.Run` pydantic object that is NOT
subscriptable -- crashed with "'Run' object is not subscriptable". Fixed here
to use attribute access (run.id, run.status, run.default_dataset_id). At
least 14 other scripts in this codebase use the same dict-style `run['x']`
pattern (grep for `run\['` across execution/ and .claude/skills/) and are
likely broken the same way on a fresh venv -- fix on sight, don't assume a
script "already works" just because it did in an older environment.
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from apify_client import ApifyClient

# Load environment variables
load_dotenv()

APIFY_API_KEY = os.getenv("APIFY_API_KEY")
ACTOR_ID = "code_crafter/leads-finder"


def scrape_leads(
    industry: str,
    max_results: int,
    filters: Optional[Dict[str, Any]] = None,
    output_file: Optional[str] = None
) -> str:
    """
    Scrape leads from Apify using the leads-finder actor.

    Args:
        industry: Target industry description
        max_results: Number of leads to scrape
        filters: Additional filters for the actor (optional)
        output_file: Path to save results (defaults to .tmp/leads_{timestamp}.json)

    Returns:
        Path to the output JSON file

    Raises:
        ValueError: If APIFY_API_KEY is not set
        Exception: If actor run fails
    """
    if not APIFY_API_KEY:
        raise ValueError("APIFY_API_KEY not found in environment variables. Please set it in .env file.")

    # Initialize Apify client
    client = ApifyClient(APIFY_API_KEY)

    # Prepare actor input using correct schema for code_crafter/leads-finder
    actor_input = {
        "fetch_count": max_results,
    }

    # Merge in custom filters if provided
    if filters:
        actor_input.update(filters)

    print(f"Starting Apify actor: {ACTOR_ID}")
    print(f"Industry: {industry}")
    print(f"Max results: {max_results}")
    print(f"Filters: {json.dumps(filters, indent=2) if filters else 'None'}")

    # Start the actor run
    try:
        # 2026-08-15: apify-client's .call() return type has flip-flopped
        # across environments -- assuming attribute-only access (run.status)
        # broke scrape_linkedin_profiles.py on this exact venv (apify-client
        # 1.12.2 returns a plain dict here, not a typed Run object). This
        # script has the identical pattern and never got exercised against
        # the bug yet, only by luck (a killed-background-task recovery this
        # session went through the raw REST API instead of this code path).
        # Handle both shapes so a future venv doesn't hit the same crash.
        run = client.actor(ACTOR_ID).call(run_input=actor_input)
        run_id = run.get('id') if isinstance(run, dict) else run.id
        run_status = run.get('status') if isinstance(run, dict) else run.status
        run_dataset_id = run.get('defaultDatasetId') if isinstance(run, dict) else run.default_dataset_id
        print(f"Actor run started. Run ID: {run_id}")
        print(f"Status: {run_status}")

        # Check if run succeeded
        if run_status != 'SUCCEEDED':
            raise Exception(f"Actor run failed with status: {run_status}")

        # Fetch results from dataset
        print("Fetching results from dataset...")
        dataset_items = client.dataset(run_dataset_id).list_items().items

        print(f"Retrieved {len(dataset_items)} leads")

        # Prepare output
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f".tmp/leads_{timestamp}.json"

        # Ensure .tmp directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Save results
        output_data = {
            "metadata": {
                "industry": industry,
                "max_results": max_results,
                "filters": filters,
                "actual_results": len(dataset_items),
                "scraped_at": datetime.now().isoformat(),
                "actor_run_id": run.id
            },
            "leads": dataset_items
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"Results saved to: {output_file}")
        return output_file

    except Exception as e:
        print(f"Error during Apify scrape: {str(e)}", file=sys.stderr)
        raise


def main():
    """CLI interface for the script."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape leads using Apify leads-finder actor")
    parser.add_argument("industry", help="Target industry description")
    parser.add_argument("--max-results", type=int, default=25, help="Number of leads to scrape")
    parser.add_argument("--output", help="Output file path (default: .tmp/leads_{timestamp}.json)")
    parser.add_argument("--filters", help="JSON string of additional filters")

    args = parser.parse_args()

    # Parse filters if provided
    filters = None
    if args.filters:
        try:
            filters = json.loads(args.filters)
        except json.JSONDecodeError as e:
            print(f"Error parsing filters JSON: {e}", file=sys.stderr)
            sys.exit(1)

    # Run the scrape
    try:
        output_file = scrape_leads(
            industry=args.industry,
            max_results=args.max_results,
            filters=filters,
            output_file=args.output
        )
        print(f"\nSuccess! Leads saved to: {output_file}")
    except Exception as e:
        print(f"\nFailed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
