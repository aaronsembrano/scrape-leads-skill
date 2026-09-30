#!/usr/bin/env python3
"""
Parallel website scraping for ICP validation.

Scrapes multiple websites concurrently using ThreadPoolExecutor.
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

load_dotenv()

TIMEOUT = 10
MAX_CONTENT_LENGTH = 5000
USER_AGENT = 'Mozilla/5.0 (compatible; ICPValidator/1.0)'
DEFAULT_WORKERS = 20


def scrape_single_website(url: str, max_content_length: int = MAX_CONTENT_LENGTH) -> Dict:
    """Scrape a single website."""
    result = {
        "url": url,
        "success": False,
        "title": "",
        "meta_description": "",
        "text_content": "",
        "error": None,
        "scraped_at": datetime.now().isoformat()
    }

    if not url or not url.startswith(('http://', 'https://')):
        result["error"] = "Invalid URL format"
        return result

    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)

        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}"
            return result

        soup = BeautifulSoup(response.content, 'html.parser')

        if soup.title:
            result["title"] = soup.title.string.strip() if soup.title.string else ""

        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            result["meta_description"] = meta_desc['content'].strip()

        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        text = soup.get_text(separator=' ', strip=True)
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)

        result["text_content"] = text[:max_content_length]
        result["success"] = True

    except requests.Timeout:
        result["error"] = "Request timeout"
    except requests.RequestException as e:
        result["error"] = f"Request error: {str(e)[:100]}"
    except Exception as e:
        result["error"] = f"Parsing error: {str(e)[:100]}"

    return result


def scrape_websites_parallel(
    leads_file: str,
    output_file: Optional[str] = None,
    workers: int = DEFAULT_WORKERS
) -> str:
    """
    Scrape websites in parallel using ThreadPoolExecutor.

    Args:
        leads_file: Path to JSON file with leads
        output_file: Path to save results
        workers: Number of parallel workers

    Returns:
        Path to output file
    """
    print(f"Loading leads from: {leads_file}")

    with open(leads_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    leads = data.get("leads", [])
    metadata = data.get("metadata", {})

    print(f"Scraping {len(leads)} websites with {workers} parallel workers...")

    # Find website column
    website_columns = ["Company Website", "Website", "company_website", "website", "website_url", "URL", "url"]
    website_key = None

    if leads:
        first_lead = leads[0]
        for col in website_columns:
            if col in first_lead:
                website_key = col
                break

    if not website_key:
        raise ValueError(f"No website column found. Looking for: {', '.join(website_columns)}")

    print(f"Using column: {website_key}")

    # Prepare scraping tasks
    results = [None] * len(leads)
    success_count = 0
    error_count = 0

    def scrape_lead(idx: int, lead: Dict) -> tuple:
        website = lead.get(website_key, "").strip()
        if not website:
            scraped = {
                "url": "",
                "success": False,
                "error": "No website URL provided",
                "title": "",
                "meta_description": "",
                "text_content": ""
            }
        else:
            scraped = scrape_single_website(website)
        return idx, lead, scraped

    # Execute in parallel
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(scrape_lead, idx, lead): idx for idx, lead in enumerate(leads)}
        completed = 0

        for future in as_completed(futures):
            idx, lead, scraped = future.result()
            results[idx] = {**lead, "scraped_content": scraped}

            if scraped["success"]:
                success_count += 1
            else:
                error_count += 1

            completed += 1
            if completed % 100 == 0 or completed == len(leads):
                print(f"Progress: {completed}/{len(leads)} ({success_count} success, {error_count} failed)")

    # Calculate statistics
    stats = {
        "total_leads": len(leads),
        "successfully_scraped": success_count,
        "failed_scrapes": error_count,
        "success_rate": round((success_count / len(leads) * 100), 2) if leads else 0
    }

    print(f"\nScraping Results:")
    print(f"  Total leads: {stats['total_leads']}")
    print(f"  Successfully scraped: {stats['successfully_scraped']}")
    print(f"  Failed scrapes: {stats['failed_scrapes']}")
    print(f"  Success rate: {stats['success_rate']}%")

    # Prepare output
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f".tmp/leads_with_content_{timestamp}.json"

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    output_data = {
        "metadata": {
            **metadata,
            "scraped_at": datetime.now().isoformat(),
            "website_column": website_key
        },
        "statistics": stats,
        "leads": results
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_file}")
    return output_file


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Parallel website scraping for ICP validation")
    parser.add_argument("leads_file", help="Path to JSON file with leads")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Number of parallel workers")

    args = parser.parse_args()

    try:
        output_file = scrape_websites_parallel(
            leads_file=args.leads_file,
            output_file=args.output,
            workers=args.workers
        )
        print(f"\n✓ Success! Results saved to: {output_file}")
    except Exception as e:
        print(f"\n✗ Failed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
