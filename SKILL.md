---
name: scrape-leads
description: Scrape B2B leads via Apify with test-then-scale validation. Use when the user wants to generate a new lead list from an industry or niche.
---

# Scrape Leads

## When to use this skill
- User wants to scrape leads for a specific industry or niche
- User asks to "find leads", "scrape leads", "get leads" for a target market
- User needs a fresh lead list before enrichment or personalization

## Scripts
- `scrape_apify_leads.py` — Scrape leads using Apify's code_crafter/leads-finder actor
- `upload_to_sheets.py` — Upload final leads JSON to a named Google Sheet
- `batch_scrape_websites.py` — Scrape company websites in parallel (20 workers)
- `scrape_websites_parallel.py` — Alternative parallel website scraper
- `execution/enrich_leads_anymailfinder.py` — Enrich leads missing emails via AnyMailFinder (shared script)

## Steps

### Step 1: Generate Initial Filters
Analyze the target industry and generate Apify filters:
- `company_industry` — array of industry strings (lowercase, valid Apify values)
- `company_keywords` — array of keywords to match in company data
- `contact_job_title` — array of job titles (lowercase)
- `size` — array of company size ranges
- `contact_location` — array of countries/regions (lowercase)
- `email_status` — always use `["validated"]`

### Step 2: Test Run (25 leads)
```bash
python3 .claude/skills/scrape-leads/scripts/scrape_apify_leads.py \
  "TARGET_INDUSTRY" \
  --max-results 25 \
  --filters '{"company_industry": [...], ...}' \
  --output ".tmp/test_leads_attempt_1.json"
```
Note: `industry` is a positional argument, not `--industry`.

### Step 3: Review Test Results (80% Threshold)
Read the test leads JSON. For each lead, evaluate whether the company name, industry, description, and job title clearly match the target ICP. Count how many pass.

**Gate: if ≥ 80% of test leads match the ICP → proceed to Step 4.**
**If < 80% match → refine filters and re-run Step 2 (max 3 attempts total).**

When retrying, diagnose why leads failed (wrong industry, wrong keywords, too broad) and tighten the filters accordingly:
- Add `company_not_keywords` to exclude off-target companies
- Narrow `company_industry` to stricter values
- Tighten `company_keywords` to more specific terms
- Narrow `contact_job_title` if wrong roles are appearing

After 3 failed attempts, proceed with the best filters found and note the quality caveat to the user.

### Step 4: Full Scrape (3,000 leads)
```bash
python3 .claude/skills/scrape-leads/scripts/scrape_apify_leads.py \
  "TARGET_INDUSTRY" \
  --max-results 3000 \
  --filters '{"company_industry": [...], ...}' \
  --output ".tmp/final_leads.json"
```
Note: `industry` is a positional argument, not `--industry`.

### Step 5: Enrich Missing Emails via AnyMailFinder
Always enrich leads that are missing emails. The enrichment script skips leads that already have an email and only calls the API for those without one.

```bash
python3 execution/enrich_leads_anymailfinder.py \
  --input ".tmp/final_leads.json" \
  --output ".tmp/final_leads_enriched.json" \
  --workers 50
```

The enrichment output is a plain JSON array. Before uploading to Sheets, wrap it in the `{metadata, leads}` format:
```python
import json
with open('.tmp/final_leads_enriched.json') as f:
    data = json.load(f)
wrapped = {
    'metadata': {'industry': 'TARGET_INDUSTRY', 'actual_results': len(data), 'enriched': True},
    'leads': data
}
with open('.tmp/final_leads_enriched_wrapped.json', 'w') as f:
    json.dump(wrapped, f, indent=2)
```

Report enrichment stats to the user: how many already had emails, how many new emails found (valid/risky), how many not found.

### Step 6: Upload to Google Sheets
```bash
python3 .claude/skills/scrape-leads/scripts/upload_to_sheets.py \
  ".tmp/final_leads_enriched_wrapped.json" \
  --name "INDUSTRY Leads - DATE"
```
Note: `leads_file` is a positional argument. Sheet name uses `--name`, not `--sheet-name`.

Return the Google Sheets URL to the user.

## Next Steps
After scraping: run `validate-leads` skill to ICP-validate, then `personalize-leads`.

## Critical Learnings

### Apify Parameter Names Are Silent Killers
Wrong parameter names don't throw errors — filters are silently ignored. Correct parameter names for `code_crafter/leads-finder`:
- `fetch_count` — number of leads (NOT `maxResults`)
- `company_industry` — industry array (NOT `industries`)
- `company_keywords` — keyword array
- `company_not_keywords` — exclusion keywords
- `contact_job_title` — job title array (NOT `job_titles`)
- `size` — company size ranges (NOT `company_sizes`)
- `contact_location` — countries/regions (NOT `countries`)
- `email_status` — always `["validated"]`

### Valid company size values
`"1-10"`, `"11-20"`, `"21-50"`, `"51-100"`, `"101-200"`, `"201-500"`, `"501-1000"`, `"1001-2000"`, `"2001-5000"`, `"5001-10000"`

### Output field names (snake_case)
`first_name`, `last_name`, `full_name`, `email`, `personal_email`, `mobile_number`, `job_title`, `seniority_level`, `linkedin`, `headline`, `company_name`, `company_website`, `company_phone`, `company_linkedin`, `industry`, `company_size`, `company_description`, `city`, `state`, `country`

### All values must be lowercase
Apify filter values are case-sensitive and must be lowercase.

### Timing Expectations
- Test scrape (25 leads): ~7-10 seconds
- Full scrape (3,000 leads): ~10-12 minutes
- Email enrichment (3,000 leads, 50 workers): ~2-3 minutes (skips leads with existing emails)
- Upload (3,000 leads): ~30 seconds

### Winning Filter Patterns by Vertical
**MSP/IT Services:**
- `company_industry`: `["information technology & services", "computer networking", "computer & network security"]`
- `company_keywords`: `["managed services", "managed service provider", "msp", "managed it"]`

**DTC/Beauty/Personal Care:**
- `company_industry`: `["cosmetics"]` (strict — "consumer goods" is too broad)
- `company_not_keywords`: `["salon", "spa", "restaurant", "cannabis", "hemp", "cbd"]`

**Manufacturing:**
- `company_industry`: `["electrical/electronic manufacturing", "mechanical or industrial engineering", "machinery", ...]`
- Use data-related keywords as proxy for technology fit since Apify has no tech stack filter

**Home Health / Hospice / Home Care:**
- `company_industry`: `["hospital & health care"]` (strict — don't add `"staffing & recruiting"` or `"health, wellness & fitness"` as they leak general staffing and fitness companies)
- `company_keywords`: `["home health", "hospice", "home care", "skilled nursing", "private duty nursing", "in-home care", "homecare", "home healthcare", "visiting nurse", "palliative care"]`
- `company_not_keywords`: `["dental", "veterinary", "salon", "spa", "fitness", "gym", "restaurant", "hotel", "real estate", "property management", "senior living advisor", "senior advisor", "consulting firm", "health tech", "placement service", "referral service", "locators", "physical therapy clinic", "nutrition", "physical rehabilitation", "software", "technology company"]`
- Tested at 92% ICP match rate

**Dental Practices (owners):**
- `company_industry`: `["medical practice", "hospital & health care", "health, wellness & fitness"]` (dental practices are spread across all three)
- `company_keywords`: `["dental", "dentist", "dentistry", "dds", "dmd", "orthodontics", "orthodontist", "periodontics", "endodontics", "oral surgery", "dental implants"]`
- `company_not_keywords`: `["addiction", "detox", "treatment center", "rehab", "behavioral health", "mental health", "psychiatry", "neurology", "neurological", "clinical research", "research institute", "sleep apnea", "sleep center", "day treatment", "dental lab", "dental laboratory", "dental supply", "dental software", "dental marketing", "dental billing", "consulting", "staffing", "insurance", "veterinary", "med spa", "chiropractic", "pharmaceutical"]`
- `contact_job_title`: `["owner", "ceo", "chief executive officer", "founder", "co-founder", "president"]`
- Tested at 88% ICP match (2026-09-25, 11-50 employees, US). Without the not-keywords, "medical practice" leaked addiction/detox centers and neurology clinics (68%). A sleep-apnea clinic still slips through; drop it by hand.

**Marketing Agencies (owners/C-suite):**
- `company_industry`: `["marketing & advertising"]`
- `company_keywords`: `["marketing agency", "digital marketing agency", "digital agency", "advertising agency", "performance marketing", "seo agency", "growth marketing", "paid media", "social media agency", "branding agency", "digital marketing", "lead generation", "ppc"]`
- `company_not_keywords`: `["software", "saas", "platform", "staffing", "recruiting", "real estate", "printing", "print", "printer", "signage", "signs", "promotional products", "promotional", "bags", "packaging", "manufacturing", "manufacturer", "displays", "trade show", "tradeshow", "exhibit", "pop display", "point of purchase", "event venue", "events", "law firm", "legal", "attorney", "nonprofit", "university", "publishing", "radio", "television", "newspaper", "magazine", "apparel", "embroidery", "inflatables", "fulfillment", "coaching"]`
- Tested at 88% ICP match (2026-09-25, 11-50 employees, US). "marketing & advertising" alone leaks printers, POP/promo-product suppliers and tradeshow-display firms (76%). About 15% of the full pull still needs hand-dropping (billboards, travel, local media sites, importers).

### Apify `contact_location` Uses State-Level Values
Country-level locations use bare names (e.g., `"united states"`), but for US state targeting use the format `"state, us"` (e.g., `"california, us"`, `"texas, us"`, `"new york, us"`). Using just the state name will fail validation.

### Apify Industry Values Use `&` Not `and`
Industry values use ampersands: `"health, wellness & fitness"` not `"health, wellness and fitness"`, `"staffing & recruiting"` not `"staffing and recruiting"`. Wrong values fail silently or throw validation errors.

### AnyMailFinder Enrichment Output Format
`enrich_leads_anymailfinder.py` outputs a plain JSON array, not the `{metadata, leads}` format that `upload_to_sheets.py` expects. Always wrap the output before uploading.
