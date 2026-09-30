# scrape-leads

A Claude Code skill that scrapes B2B leads via Apify (`code_crafter/leads-finder`) using a test-then-scale workflow: 25-lead test run, LLM review against an 80% ICP-match gate, then a full scrape and Google Sheets upload.

## Install
Copy this folder to `.claude/skills/scrape-leads/` in your project, then:

```bash
pip install -r requirements.txt
cp .env.example .env   # add your APIFY_API_KEY
```

For the Google Sheets upload, create your own OAuth client in Google Cloud Console, save it as `credentials.json` in the project root, and the first run generates `token.json`. Both are git-ignored.

See [SKILL.md](SKILL.md) for the full workflow. The optional email-enrichment step references a shared AnyMailFinder script (`execution/enrich_leads_anymailfinder.py`) that is not included here.
