#!/usr/bin/env python3
"""
Example script showing how to use the JIRA to ClickUp importer.
"""

import os
from dotenv import load_dotenv
from jira_to_clickup import JiraToClickUpImporter

def example_usage():
    """Example of how to use the importer programmatically"""
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get configuration from environment variables
    API_TOKEN = os.getenv('CLICKUP_API_TOKEN')
    LIST_ID = os.getenv('CLICKUP_LIST_ID')
    XML_FILE = os.getenv('JIRA_XML_FILE', 'sisr-export.xml')
    JIRA_BASE_URL = os.getenv('JIRA_BASE_URL')
    JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
    JIRA_EMAIL = os.getenv('JIRA_EMAIL')
    
    # Validate required environment variables
    if not API_TOKEN:
        print("Error: CLICKUP_API_TOKEN environment variable is required")
        print("Please set it in your .env file or environment")
        return
    
    if not LIST_ID:
        print("Error: CLICKUP_LIST_ID environment variable is required")
        print("Please set it in your .env file or environment")
        return
    
    # Warn about optional JIRA configuration for attachments
    if not JIRA_BASE_URL or not JIRA_API_TOKEN or not JIRA_EMAIL:
        print("⚠️  WARNING: JIRA_BASE_URL, JIRA_API_TOKEN, or JIRA_EMAIL not configured")
        print("   Attachments will be skipped during import")
        print("   Set these in your .env file to enable attachment downloads")
    
    # Create the importer
    importer = JiraToClickUpImporter(API_TOKEN, LIST_ID, JIRA_BASE_URL, JIRA_API_TOKEN, JIRA_EMAIL)
    
    try:
        # Parse the JIRA XML
        print("Parsing JIRA XML...")
        tasks = importer.parse_jira_xml(XML_FILE)
        print(f"Found {len(tasks)} tasks to import")
        
        # First, do a dry run to see what would be imported
        print("\nDoing dry run...")
        importer.import_tasks(tasks, dry_run=True)
        
        # Ask for confirmation
        response = input("\nDo you want to proceed with the actual import? (y/N): ")
        if response.lower() == 'y':
            print("\nStarting actual import...")
            importer.import_tasks(tasks, dry_run=False)
        else:
            print("Import cancelled.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    example_usage() 