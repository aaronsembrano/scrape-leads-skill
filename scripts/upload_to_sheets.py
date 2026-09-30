#!/usr/bin/env python3
"""
Upload validated leads to Google Sheets.

This script creates a new Google Sheet, uploads lead data with validation
status, and returns a shareable link.
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Google Sheets API scopes
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def get_google_credentials() -> Credentials:
    """
    Get or refresh Google OAuth credentials.

    Returns:
        Valid Google credentials

    Raises:
        FileNotFoundError: If credentials.json is missing
    """
    creds = None

    # Check if token.json exists (previously authenticated)
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError(
                    "credentials.json not found. Please download it from Google Cloud Console.\n"
                    "See README.md for setup instructions."
                )
            print("Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            # Use run_local_server first, but if it fails or we want to be safe, we can use run_console
            # However, run_console is often deprecated in newer versions.
            # Let's try run_local_server with open_browser=False if possible, or just catch it.
            try:
                creds = flow.run_local_server(port=0, open_browser=False)
            except Exception:
                print("Local server failed, trying console flow...")
                creds = flow.run_console()

        # Save credentials for future use
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def prepare_sheet_data(leads_data: Dict[str, Any]) -> tuple[List[str], List[List[Any]]]:
    """
    Convert leads data to Google Sheets format.

    Args:
        leads_data: Dictionary with validation results

    Returns:
        Tuple of (headers, rows)
    """
    # Extract leads - could be from validation results or raw leads
    if "results" in leads_data:
        # Validated leads format
        leads = leads_data["results"]
        include_validation = True
    else:
        # Raw leads format
        leads = leads_data.get("leads", [])
        include_validation = False

    if not leads:
        return [], []

    # Define headers based on actual Apify leads-finder output
    base_headers = [
        "First Name",
        "Last Name",
        "Full Name",
        "Email",
        "Personal Email",
        "Mobile Number",
        "Job Title",
        "Seniority Level",
        "LinkedIn",
        "Company Name",
        "Company Website",
        "Company Phone",
        "Company LinkedIn",
        "Industry",
        "Company Size",
        "City",
        "State",
        "Country",
        "Company Description",
        "Headline"
    ]

    if include_validation:
        base_headers.extend(["Validation Status", "Confidence Score", "Validation Reason"])

    # Convert leads to rows
    rows = []
    for item in leads:
        # Handle both validated and raw lead formats
        if include_validation:
            lead = item.get("lead", {})
            is_valid = item.get("is_valid", False)
            confidence = item.get("confidence", 0.0)
            reason = item.get("reason", "")
        else:
            lead = item
            is_valid = None
            confidence = None
            reason = None
            
        # Filter out dummy apify items
        if lead.get("fullName", "").startswith("🟢"):
            continue

        # Extract fields - supports multiple naming conventions:
        # 1. Title Case (from Google Sheet reads): "First Name", "Company Name"
        # 2. snake_case (from Apify): first_name, company_name
        # 3. camelCase (from some Apify actors): firstName, companyName
        main_email = lead.get("Email", lead.get("email", lead.get("workEmail", "")))

        row = [
            lead.get("First Name", lead.get("first_name", lead.get("firstName", ""))),
            lead.get("Last Name", lead.get("last_name", lead.get("lastName", ""))),
            lead.get("Full Name", lead.get("full_name", lead.get("fullName", ""))),
            main_email,
            lead.get("Personal Email", lead.get("personal_email", lead.get("personalEmail", ""))),
            lead.get("Mobile Number", lead.get("mobile_number", lead.get("mobileNumber", lead.get("phone", "")))),
            lead.get("Job Title", lead.get("job_title", lead.get("jobTitle", lead.get("position", "")))),
            lead.get("Seniority Level", lead.get("seniority_level", lead.get("seniority", ""))),
            lead.get("LinkedIn", lead.get("linkedin", lead.get("linkedinUrl", ""))),
            lead.get("Company Name", lead.get("company_name", lead.get("organizationName", lead.get("companyName", "")))),
            lead.get("Company Website", lead.get("company_website", lead.get("organizationWebsite", lead.get("companyWebsite", "")))),
            lead.get("Company Phone", lead.get("company_phone", lead.get("organizationPhone", lead.get("companyPhone", "")))),
            lead.get("Company LinkedIn", lead.get("company_linkedin", lead.get("organizationLinkedinUrl", lead.get("companyLinkedinUrl", "")))),
            lead.get("Industry", lead.get("industry", lead.get("organizationIndustry", ""))),
            lead.get("Company Size", lead.get("company_size", lead.get("organizationSize", lead.get("companyEmployeeSize", "")))),
            lead.get("City", lead.get("city", lead.get("organizationCity", ""))),
            lead.get("State", lead.get("state", lead.get("organizationState", ""))),
            lead.get("Country", lead.get("country", lead.get("organizationCountry", ""))),
            lead.get("Company Description", lead.get("company_description", lead.get("organizationDescription", lead.get("companyDescription", "")))),
            lead.get("Headline", lead.get("headline", ""))
        ]

        if include_validation:
            row.extend([
                "Valid" if is_valid else "Invalid",
                f"{confidence:.2f}" if confidence is not None else "",
                reason or ""
            ])

        rows.append(row)

    return base_headers, rows


def upload_to_sheets(
    leads_file: str,
    sheet_name: Optional[str] = None
) -> str:
    """
    Upload leads to a new Google Sheet.

    Args:
        leads_file: Path to JSON file with leads
        sheet_name: Name for the Google Sheet (optional)

    Returns:
        URL of the created Google Sheet

    Raises:
        FileNotFoundError: If leads_file or credentials.json doesn't exist
        HttpError: If Google Sheets API call fails
    """
    # Load leads data
    print(f"Loading leads from: {leads_file}")
    with open(leads_file, 'r', encoding='utf-8') as f:
        leads_data = json.load(f)

    # Prepare sheet data
    headers, rows = prepare_sheet_data(leads_data)

    if not rows:
        raise ValueError("No leads found in the input file")

    print(f"Preparing to upload {len(rows)} leads to Google Sheets...")

    # Get credentials
    creds = get_google_credentials()

    # Build Google Sheets service
    service = build('sheets', 'v4', credentials=creds)

    # Create sheet name if not provided
    if not sheet_name:
        metadata = leads_data.get("metadata", {})
        industry = metadata.get("industry", "Unknown")
        timestamp = datetime.now().strftime("%Y-%m-%d")
        sheet_name = f"{industry} Leads - {timestamp}"

    try:
        # Create new spreadsheet
        print(f"Creating spreadsheet: {sheet_name}")
        spreadsheet = {
            'properties': {'title': sheet_name}
        }
        spreadsheet = service.spreadsheets().create(
            body=spreadsheet,
            fields='spreadsheetId,spreadsheetUrl'
        ).execute()

        spreadsheet_id = spreadsheet.get('spreadsheetId')
        spreadsheet_url = spreadsheet.get('spreadsheetUrl')

        print(f"Spreadsheet created: {spreadsheet_id}")

        # Prepare data with headers
        values = [headers] + rows

        # Upload data
        print("Uploading data...")
        body = {'values': values}
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='A1',
            valueInputOption='RAW',
            body=body
        ).execute()

        # Format header row (bold, freeze)
        requests = [
            {
                'repeatCell': {
                    'range': {
                        'sheetId': 0,
                        'startRowIndex': 0,
                        'endRowIndex': 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'textFormat': {'bold': True}
                        }
                    },
                    'fields': 'userEnteredFormat.textFormat.bold'
                }
            },
            {
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': 0,
                        'gridProperties': {'frozenRowCount': 1}
                    },
                    'fields': 'gridProperties.frozenRowCount'
                }
            }
        ]

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()

        print(f"\nSuccess! Uploaded {len(rows)} leads")
        print(f"Google Sheets URL: {spreadsheet_url}")

        return spreadsheet_url

    except HttpError as error:
        print(f"Google Sheets API error: {error}", file=sys.stderr)
        raise


def main():
    """CLI interface for the script."""
    import argparse

    parser = argparse.ArgumentParser(description="Upload leads to Google Sheets")
    parser.add_argument("leads_file", help="Path to JSON file with leads")
    parser.add_argument("--name", help="Name for the Google Sheet")

    args = parser.parse_args()

    try:
        url = upload_to_sheets(
            leads_file=args.leads_file,
            sheet_name=args.name
        )
        print(f"\n✓ Sheet URL: {url}")
    except Exception as e:
        print(f"\nFailed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
