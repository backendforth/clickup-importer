# JIRA to ClickUp Importer

This project provides tools to export JIRA tasks and import them into ClickUp through their REST API.

## Features

- Parse JIRA XML exports
- Convert task data to ClickUp format
- Import tasks with descriptions, comments, priorities, and tags
- **Download and upload attachments** from JIRA to ClickUp
- **Resolve user names** in comments (shows actual names instead of account IDs)
- Support for dry-run mode to preview imports
- Rate limiting to respect ClickUp API limits
- Comprehensive error handling and logging

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get ClickUp API Token

1. Go to ClickUp and click on your avatar
2. Select "Apps" from the dropdown
3. Click "Generate" next to "API Token"
4. Copy the generated token

### 3. Get ClickUp List ID

1. Open the ClickUp list where you want to import tasks
2. The List ID is in the URL: `https://app.clickup.com/{team_id}/v/li/{list_id}`
3. Copy the `list_id` part

### 4. Get JIRA API Token (Optional - for attachment downloads)

1. Go to your Atlassian account: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a descriptive name (e.g., "ClickUp Import")
4. Copy the generated token

**Note:** Without JIRA configuration, the script will still import tasks but skip attachments.

### 5. Configure Environment Variables (Recommended)

Create a `.env` file in the project root to store your configuration:

```bash
# Copy the template
cp env.example .env
```

Edit the `.env` file with your actual values:

```bash
# ClickUp API Configuration
CLICKUP_API_TOKEN=your_actual_api_token_here
CLICKUP_LIST_ID=your_actual_list_id_here

# JIRA Configuration (for attachment downloads)
JIRA_BASE_URL=https://your-domain.atlassian.net/
JIRA_API_TOKEN=your_jira_api_token_here
JIRA_EMAIL=your.email@example.com

# Optional: Default XML file path
JIRA_XML_FILE=sisr-export.xml
```

**Benefits of using .env file:**
- No need to pass API token and list ID as command line arguments
- Keeps sensitive data out of command history
- Easier to manage multiple configurations
- More secure than hardcoding values

## Usage

### Command Line Interface

#### Using Environment Variables (Recommended)

If you've set up your `.env` file, you can run the importer with minimal commands:

```bash
# Dry run (preview what would be imported)
python jira_to_clickup.py --dry-run

# Actual import
python jira_to_clickup.py

# Use a different XML file
python jira_to_clickup.py path/to/other-export.xml --dry-run

# Enable verbose debug output
python jira_to_clickup.py --dry-run --verbose

# List available custom fields
python jira_to_clickup.py --list-custom-fields
```

#### Using Command Line Arguments

You can still use command line arguments if preferred:

```bash
# Dry run (preview what would be imported)
python jira_to_clickup.py sisr-export.xml --api-token YOUR_API_TOKEN --list-id YOUR_LIST_ID --dry-run

# Actual import
python jira_to_clickup.py sisr-export.xml --api-token YOUR_API_TOKEN --list-id YOUR_LIST_ID
```

**Note:** Command line arguments override environment variables if both are provided.

### Available Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--dry-run` | | Show what would be imported without actually creating tasks |
| `--verbose` | `-v` | Enable detailed debugging output for troubleshooting |
| `--list-custom-fields` | | List all custom fields in the ClickUp list (helps find field IDs) |
| `--api-token` | | ClickUp API token (overrides environment variable) |
| `--list-id` | | ClickUp List ID (overrides environment variable) |

#### Verbose Mode

Use `--verbose` or `-v` to enable detailed debugging output. This is helpful for:
- Troubleshooting import issues
- Understanding API responses
- Monitoring task creation progress
- Debugging custom field mappings

```bash
# Verbose dry run
python jira_to_clickup.py --dry-run --verbose

# Verbose actual import  
python jira_to_clickup.py --verbose
```

**Note:** Without verbose mode, only essential progress information is shown for cleaner output.

### Programmatic Usage

#### Using Environment Variables (Recommended)

```python
import os
from dotenv import load_dotenv
from jira_to_clickup import JiraToClickUpImporter

# Load environment variables
load_dotenv()

# Get configuration from environment
api_token = os.getenv('CLICKUP_API_TOKEN')
list_id = os.getenv('CLICKUP_LIST_ID')
xml_file = os.getenv('JIRA_XML_FILE', 'sisr-export.xml')

# Initialize importer
importer = JiraToClickUpImporter(api_token, list_id)

# Initialize importer with verbose debug output
# importer = JiraToClickUpImporter(api_token, list_id, verbose=True)

# Parse JIRA XML
tasks = importer.parse_jira_xml(xml_file)

# Import tasks (dry run first)
importer.import_tasks(tasks, dry_run=True)
importer.import_tasks(tasks, dry_run=False)
```

#### Using Direct Values

```python
from jira_to_clickup import JiraToClickUpImporter

# Initialize importer with direct values
importer = JiraToClickUpImporter("your_api_token", "your_list_id")

# Initialize importer with verbose debug output
# importer = JiraToClickUpImporter("your_api_token", "your_list_id", verbose=True)

# Parse JIRA XML
tasks = importer.parse_jira_xml("sisr-export.xml")

# Import tasks (dry run first)
importer.import_tasks(tasks, dry_run=True)
importer.import_tasks(tasks, dry_run=False)
```

## Data Mapping

### JIRA → ClickUp Field Mapping

| JIRA Field | ClickUp Field | Notes |
|------------|---------------|-------|
| Summary | Task Name | Prefixed with JIRA key |
| Description + Comments | Task Description | Combined with markdown formatting |
| Priority | Priority | Mapped to ClickUp priority levels (1-4) |
| Status | Tags | Added as status tag |
| Project Key | Tags | Added as project tag |
| Assignee | Tags | Added as assignee tag |
| Due Date | Due Date | Converted to Unix timestamp |

### Priority Mapping

| JIRA Priority | ClickUp Priority |
|---------------|------------------|
| Highest | 1 (Urgent) |
| High | 2 (High) |
| Medium | 3 (Normal) |
| Low | 4 (Low) |
| Lowest | 4 (Low) |

## Output

The script provides detailed progress information including:

- Number of tasks found and processed
- Success/failure status for each task
- Created ClickUp task IDs
- Summary of successful and failed imports

## Rate Limiting

The script includes built-in rate limiting to respect ClickUp API limits:
- 1 second delay between task creations
- 0.5 second delay between comment additions

## Error Handling

- Comprehensive error messages for API failures
- Graceful handling of malformed XML data
- Detailed logging of failed imports with reasons

## Files

- `jira_to_clickup.py` - Main importer script
- `jira_to_excel.py` - Original JIRA to Excel converter
- `example_import.py` - Example usage script
- `requirements.txt` - Python dependencies
- `sisr-export.xml` - JIRA XML export file

## Troubleshooting

### Common Issues

1. **Invalid API Token**
   - Verify your ClickUp API token is correct
   - Ensure the token has proper permissions

2. **Invalid List ID**
   - Check that the List ID is correct
   - Ensure you have access to the target list

3. **Rate Limiting**
   - If you encounter rate limit errors, the script will show detailed error messages
   - Consider reducing the number of tasks imported at once

4. **XML Parsing Errors**
   - Ensure the XML file is a valid JIRA export
   - Check that the file is not corrupted

### Debug Mode

For detailed debugging, you can modify the script to enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Notes

- **Never commit API tokens to version control**
- **Always use `.env` file for sensitive data** - the `.env` file is automatically ignored by git
- The `env.example` template file can be safely committed as it contains no actual credentials
- Environment variables are the preferred method for configuration in production environments
- If using manual environment variables, set them in your shell:

```bash
export CLICKUP_API_TOKEN="your_token_here"
export CLICKUP_LIST_ID="your_list_id_here"
```

## License

This project is provided as-is for educational and utility purposes. 