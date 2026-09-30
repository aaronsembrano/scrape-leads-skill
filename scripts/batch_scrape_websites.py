#!/usr/bin/env python3
"""Batch scrape websites from leads using parallel processing."""

import json
import sys
from datetime import datetime
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from scrape_website import scrape_website

# Additional pages to scrape for more context
ADDITIONAL_PAGES = ['/about', '/about-us', '/services', '/what-we-do']


def scrape_single_lead(lead, idx, total, multi_page=False):
    """Scrape website for a single lead (to be run in parallel)."""
    # Handle multiple possible field names (case-insensitive)
    company = (lead.get('Company Name') or lead.get('Company_Name') or lead.get('Company') or lead.get('company') or
               lead.get('organizationName', ''))
    website = (lead.get('Company Website') or lead.get('Company_Website') or lead.get('Website') or lead.get('website') or
               lead.get('corporate website') or lead.get('Corporate Website') or
               lead.get('organizationWebsite', ''))

    result = lead.copy()

    if website:
        try:
            # Normalize URL
            if not website.startswith(('http://', 'https://')):
                website = 'https://' + website

            # Scrape homepage
            scraped = scrape_website(website)

            # If multi-page mode and homepage succeeded, try additional pages
            if multi_page and scraped['success']:
                additional_content = []
                base_url = f"{urlparse(website).scheme}://{urlparse(website).netloc}"

                for page_path in ADDITIONAL_PAGES:
                    page_url = urljoin(base_url, page_path)
                    try:
                        page_scraped = scrape_website(page_url)
                        if page_scraped['success'] and page_scraped.get('text_content'):
                            additional_content.append(page_scraped['text_content'][:1500])
                    except Exception:
                        pass  # Silently skip failed additional pages

                # Combine content
                if additional_content:
                    combined_text = scraped.get('text_content', '')
                    for extra in additional_content:
                        combined_text += f"\n\n{extra}"
                    scraped['text_content'] = combined_text[:8000]  # Cap at 8000 chars
                    scraped['pages_scraped'] = 1 + len(additional_content)

            result['website_content'] = scraped

            if scraped['success']:
                pages_info = f" ({scraped.get('pages_scraped', 1)} pages)" if multi_page and scraped.get('pages_scraped', 1) > 1 else ""
                status = f"✓ scraped{pages_info}"
            else:
                status = f"⊘ {scraped.get('error', 'failed')}"

            print(f'[{idx}/{total}] {company[:40]}... {status}')
            return result, scraped['success']

        except Exception as e:
            print(f'[{idx}/{total}] {company[:40]}... ✗ error: {str(e)}')
            result['website_content'] = {
                'url': website,
                'success': False,
                'error': str(e),
                'title': '',
                'meta_description': '',
                'text_content': ''
            }
            return result, False
    else:
        print(f'[{idx}/{total}] {company[:40]}... ⊘ no website')
        result['website_content'] = {
            'url': '',
            'success': False,
            'error': 'No website URL provided',
            'title': '',
            'meta_description': '',
            'text_content': ''
        }
        return result, False

def main():
    leads_file = sys.argv[1] if len(sys.argv) > 1 else '.tmp/sheet_leads.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else '.tmp/leads_with_content.json'
    max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    # Check for --multi-page flag
    multi_page = '--multi-page' in sys.argv or '-m' in sys.argv

    # Load leads
    with open(leads_file, 'r') as f:
        data = json.load(f)

    leads = data.get('leads', [])

    mode_str = " (multi-page mode)" if multi_page else ""
    print(f'Scraping {len(leads)} websites in parallel (max {max_workers} workers){mode_str}...\n')

    results = []
    success_count = 0

    # Process leads in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(scrape_single_lead, lead, idx, len(leads), multi_page): idx
            for idx, lead in enumerate(leads, 1)
        }

        # Collect results as they complete
        for future in as_completed(futures):
            result, success = future.result()
            results.append(result)
            if success:
                success_count += 1

    # Sort results back to original order by row_number if available
    if results and 'row_number' in results[0]:
        results.sort(key=lambda x: x.get('row_number', 0))

    # Save
    metadata = data.get('metadata', {})
    metadata['scraped_at'] = datetime.now().isoformat()
    metadata['scrape_success_count'] = success_count
    metadata['scrape_total'] = len(leads)
    metadata['scrape_success_rate'] = f"{(success_count/len(leads)*100):.1f}%"

    output = {
        'metadata': metadata,
        'leads': results
    }

    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'\n✓ Scraped {success_count}/{len(leads)} websites ({success_count/len(leads)*100:.1f}% success rate)')
    print(f'✓ Results saved to: {output_file}')

if __name__ == '__main__':
    main()
