#!/usr/bin/env python3
"""
JIRA XML to ClickUp Importer
Extracts tasks from JIRA XML export and creates them in ClickUp via REST API.
"""

import requests
import json
import re
import html
import time
import tempfile
import mimetypes
from datetime import datetime
from lxml import etree
import argparse
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv

class JiraToClickUpImporter:
    def __init__(self, api_token: str, list_id: str, jira_base_url: str = None, jira_api_token: str = None, jira_email: str = None, verbose: bool = False):
        """
        Initialize the importer with ClickUp and JIRA API credentials.
        
        Args:
            api_token: ClickUp API token
            list_id: ClickUp List ID where tasks will be created
            jira_base_url: JIRA base URL (e.g. https://umwerk.atlassian.net/)
            jira_api_token: JIRA API token for downloading attachments
            jira_email: Email address for JIRA basic authentication
            verbose: Enable detailed debug output
        """
        self.api_token = api_token
        self.list_id = list_id
        self.jira_base_url = jira_base_url.rstrip('/') if jira_base_url else None
        self.jira_api_token = jira_api_token
        self.verbose = verbose
        self.base_url = "https://api.clickup.com/api/v2"
        
        # Handle ClickUp API token - add pk_ prefix only if not already present
        auth_token = api_token if api_token.startswith('pk_') else f"pk_{api_token}"
        self.debug(f"🔍 DEBUG - Token processing: input='{api_token[:15]}...', output='{auth_token[:15]}...'")
        self.headers = {
            "Authorization": auth_token,
            "Content-Type": "application/json"
        }
        
        # JIRA API headers for attachment download
        # Note: JIRA requires email+token basic auth, not Bearer token
        self.jira_email = jira_email
        self.jira_headers = {
            "Accept": "application/json"
        } if jira_api_token else None
        
        self.created_tasks = []
        self.failed_tasks = []
        self.user_mapping = {}  # Maps account IDs to display names
        
        # Priority mapping from JIRA to ClickUp
        self.priority_mapping = {
            "Highest": 1,
            "High": 2,
            "Medium": 3,
            "Low": 4,
            "Lowest": 4
        }
        
        # Status mapping from JIRA to ClickUp
        # Mapped to your specific ClickUp statuses: backlog, waiting/blocked, ready for action, work in progress, in review, done
        self.status_mapping = {
            "To Do": "ready for action",
            "Open": "ready for action", 
            "Backlog": "backlog",
            "Ready": "ready for action",
            "In Progress": "work in progress",
            "In Review": "in review",
            "Review": "in review",
            "Testing": "in review",
            "QA": "in review",
            "Done": "done",
            "Closed": "done",
            "Resolved": "done",
            "Complete": "done",
            "Completed": "done",
            "Cancelled": "done",
            "Won't Do": "done",
            "Blocked": "waiting/blocked",
            "Waiting": "waiting/blocked",
            "On Hold": "waiting/blocked"
        }
        
        # Custom field configuration
        # Note: You need to get the actual custom field ID from your ClickUp list
        # To get the field ID, use the ClickUp API or browser dev tools:
        # 1. Go to your ClickUp list settings
        # 2. Find the "Jira Assignee" custom field
        # 3. Use browser dev tools to inspect the field and find its ID
        # 4. Or use: GET https://api.clickup.com/api/v2/list/{list_id}/field
        self.custom_fields = {
            "jira_assignee_field_id": "8385553f-b815-469f-9258-f1102e1f9239"  # Jira Assignee custom field
        }
    
    def debug(self, message: str) -> None:
        """Print debug message only if verbose mode is enabled"""
        if self.verbose:
            print(message)
    
    def build_user_mapping(self, root) -> None:
        """Build mapping of account IDs to display names from XML"""
        self.user_mapping = {}
        
        # Find all assignee and reporter elements to build user mapping
        items = root.findall('.//item')
        for item in items:
            # Map assignees
            assignee_elem = item.find('assignee')
            if assignee_elem is not None:
                account_id = assignee_elem.get('accountid', '')
                display_name = assignee_elem.text or ''
                if account_id and display_name:
                    self.user_mapping[account_id] = display_name
            
            # Map reporters
            reporter_elem = item.find('reporter')
            if reporter_elem is not None:
                account_id = reporter_elem.get('accountid', '')
                display_name = reporter_elem.text or ''
                if account_id and display_name:
                    self.user_mapping[account_id] = display_name
        
        self.debug(f"🔍 DEBUG - Built user mapping with {len(self.user_mapping)} users: {self.user_mapping}")
    
    def resolve_user_name(self, account_id: str) -> str:
        """Resolve account ID to display name"""
        return self.user_mapping.get(account_id, account_id)
    
    def extract_attachments(self, item) -> List[Dict]:
        """Extract all attachments from an item"""
        attachments = []
        attachment_elements = item.findall('.//attachment')
        
        for attachment_elem in attachment_elements:
            attachment_id = attachment_elem.get('id', '')
            name = attachment_elem.get('name', '')
            size = attachment_elem.get('size', '')
            author = attachment_elem.get('author', '')
            created = self.parse_date(attachment_elem.get('created', ''))
            
            attachment_data = {
                'id': attachment_id,
                'name': name,
                'size': int(size) if size.isdigit() else 0,
                'author': self.resolve_user_name(author),
                'author_id': author,
                'created': created
            }
            attachments.append(attachment_data)
        
        return attachments
    
    def download_jira_attachment(self, attachment_id: str, filename: str) -> Optional[str]:
        """Download attachment from JIRA and return path to temporary file"""
        if not self.jira_base_url or not self.jira_api_token:
            self.debug("⚠️  WARNING: JIRA base URL or API token not configured, skipping attachment download")
            return None
        
        if not self.jira_email:
            self.debug("⚠️  WARNING: JIRA_EMAIL not configured, skipping attachment download")
            print("❌ ERROR: JIRA_EMAIL environment variable is required for attachment downloads")
            print("   Set your Atlassian account email in JIRA_EMAIL environment variable")
            return None
        
        url = f"{self.jira_base_url}/rest/api/3/attachment/content/{attachment_id}"
        
        try:
            self.debug(f"🔍 DEBUG - Downloading attachment {attachment_id} from {url}")
            self.debug(f"🔍 DEBUG - Using email: {self.jira_email}")
            
            # Use basic authentication with email and API token
            response = requests.get(
                url, 
                headers=self.jira_headers, 
                auth=(self.jira_email, self.jira_api_token),
                stream=True
            )
            response.raise_for_status()
            
            # Create temporary file
            suffix = os.path.splitext(filename)[1] if '.' in filename else ''
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            
            # Write content to temporary file
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            
            temp_file.close()
            self.debug(f"✅ DEBUG - Successfully downloaded attachment to {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            print(f"❌ ERROR downloading attachment {attachment_id}: {e}")
            return None
    
    def upload_clickup_attachment(self, task_id: str, file_path: str, filename: str) -> bool:
        """Upload attachment to ClickUp task"""
        url = f"{self.base_url}/task/{task_id}/attachment"
        
        try:
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            self.debug(f"🔍 DEBUG - Uploading attachment {filename} to task {task_id}")
            
            # Prepare headers for file upload (remove Content-Type to let requests set it)
            upload_headers = {
                "Authorization": self.headers["Authorization"]
            }
            
            with open(file_path, 'rb') as f:
                files = {
                    'attachment': (filename, f, mime_type)
                }
                
                response = requests.post(url, headers=upload_headers, files=files)
                response.raise_for_status()
                
                self.debug(f"✅ DEBUG - Successfully uploaded attachment {filename}")
                return True
                
        except Exception as e:
            print(f"❌ ERROR uploading attachment {filename}: {e}")
            return False
    
    def clean_html(self, text: str) -> str:
        """Remove HTML tags and decode HTML entities"""
        if not text:
            return ""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities
        text = html.unescape(text)
        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def extract_html_content(self, element) -> str:
        """Extract HTML content from an element, preserving the HTML structure"""
        if element is None:
            return ""
        
        # Get the text content including HTML tags
        content = etree.tostring(element, encoding='unicode', method='html')
        
        # Remove the outer tag
        tag_name = element.tag
        content = re.sub(f'^<{tag_name}[^>]*>', '', content)
        content = re.sub(f'</{tag_name}>$', '', content)
        
        return content.strip()
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse JIRA date format to Python datetime"""
        if not date_str:
            return None
        try:
            # Jira format: "Wed, 9 Jul 2025 14:31:57 +0200"
            return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        except:
            return None
    
    def extract_comments(self, item) -> List[Dict]:
        """Extract all comments from an item"""
        comments = []
        comment_elements = item.findall('.//comment')
        
        for comment_elem in comment_elements:
            comment_id = comment_elem.get('id', '')
            author_id = comment_elem.get('author', '')
            author_name = self.resolve_user_name(author_id)
            created = self.parse_date(comment_elem.get('created', ''))
            content = self.extract_html_content(comment_elem)
            
            comment_data = {
                'id': comment_id,
                'author': author_name,
                'author_id': author_id,
                'created': created,
                'content': self.clean_html(content)
            }
            comments.append(comment_data)
        
        return comments
    
    def create_task_description(self, description: str, created_date: Optional[datetime], assignee: str, reporter: str) -> str:
        """Create a markdown description with original description and metadata"""
        parts = []
        
        # Add metadata section
        metadata_parts = []
        
        if created_date:
            date_str = created_date.strftime('%B %d, %Y at %H:%M') if isinstance(created_date, datetime) else str(created_date)
            metadata_parts.append(f"**Created:** {date_str}")
        
        if assignee:
            metadata_parts.append(f"**Assignee:** {assignee}")
            
        if reporter:
            metadata_parts.append(f"**Reporter:** {reporter}")
        
        if metadata_parts:
            parts.append('\n'.join(metadata_parts))
        
        # Add original description
        if description:
            clean_desc = self.clean_html(description)
            if clean_desc:
                parts.append(f"## Description\n\n{clean_desc}")
        
        return '\n\n'.join(parts)
    
    def map_priority(self, jira_priority: str) -> int:
        """Map JIRA priority to ClickUp priority (1=urgent, 2=high, 3=normal, 4=low)"""
        return self.priority_mapping.get(jira_priority, 3)  # Default to normal priority
    
    def map_status(self, jira_status: str) -> Optional[str]:
        """Map JIRA status to ClickUp status"""
        return self.status_mapping.get(jira_status)
    
    def get_list_custom_fields(self) -> Optional[Dict]:
        """Get custom fields for the ClickUp list (helper method)"""
        url = f"{self.base_url}/list/{self.list_id}/field"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            
            print("📋 Available custom fields in your ClickUp list:")
            for field in result.get('fields', []):
                field_name = field.get('name')
                field_id = field.get('id')
                field_type = field.get('type')
                print(f"  - Name: '{field_name}', ID: {field_id}, Type: {field_type}")
                
                # Show detailed info for labels fields
                if field_type == 'labels' and field_name == 'Jira Assignee':
                    print(f"    📄 Detailed info for '{field_name}':")
                    type_config = field.get('type_config', {})
                    options = type_config.get('options', [])
                    print(f"    📄 Current options ({len(options)} total):")
                    for option in options:
                        option_id = option.get('id')
                        option_name = option.get('name')
                        option_color = option.get('color')
                        print(f"      - ID: {option_id}, Name: '{option_name}', Color: {option_color}")
                    
                    # Check if new options can be created
                    if type_config.get('allow_create_options'):
                        print(f"    ✅ This field allows creating new options automatically")
                    else:
                        print(f"    ❌ This field requires using existing option IDs only")
            
            return result
        except requests.exceptions.RequestException as e:
            print(f"❌ ERROR getting custom fields: {e}")
            return None
    
    def get_clickup_user_mapping(self) -> Dict[str, str]:
        """Get mapping of user names to ClickUp custom field option IDs"""
        if hasattr(self, '_clickup_user_mapping'):
            return self._clickup_user_mapping
        
        self._clickup_user_mapping = {}
        
        # Get custom field details
        url = f"{self.base_url}/list/{self.list_id}/field"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            
            # Find the Jira Assignee field
            for field in result.get('fields', []):
                if field.get('id') == self.custom_fields["jira_assignee_field_id"]:
                    type_config = field.get('type_config', {})
                    options = type_config.get('options', [])
                    
                    # Build mapping: user name -> option ID
                    for option in options:
                        user_name = option.get('name') or option.get('label')
                        option_id = option.get('id')
                        if user_name and option_id and user_name != 'None':
                            self._clickup_user_mapping[user_name] = option_id
                    
                    self.debug(f"🔍 DEBUG - Built ClickUp user mapping with {len(self._clickup_user_mapping)} users")
                    break
                    
        except Exception as e:
            self.debug(f"🔍 DEBUG - Could not build ClickUp user mapping: {e}")
        
        return self._clickup_user_mapping

    def create_custom_fields(self, assignee: str) -> List[Dict]:
        """Create custom fields array for ClickUp task"""
        custom_fields = []
        
        # Add Jira Assignee custom field
        if assignee:
            if self.custom_fields["jira_assignee_field_id"]:
                # Try to map the assignee to a ClickUp option ID
                user_mapping = self.get_clickup_user_mapping()
                option_id = user_mapping.get(assignee)
                
                if option_id:
                    # We found a matching option, use it
                    custom_fields.append({
                        "id": self.custom_fields["jira_assignee_field_id"],
                        "value": [option_id]
                    })
                    self.debug(f"🔍 DEBUG - Mapped assignee '{assignee}' to option ID '{option_id}'")
                else:
                    # No mapping found, skip custom field but mention it
                    self.debug(f"🔍 DEBUG - No ClickUp option found for assignee '{assignee}', using description instead")
                    print(f"💡 INFO: Assignee '{assignee}' will be shown in task description (no matching ClickUp option)")
            else:
                # Warn if custom field ID is not configured
                print(f"⚠️  WARNING: Jira Assignee custom field ID not configured. Assignee '{assignee}' will only appear in description.")
                print("💡 Run with --list-custom-fields to find the field ID")
        
        return custom_fields
    
    def create_clickup_task(self, task_data: Dict) -> Optional[Dict]:
        """Create a task in ClickUp"""
        url = f"{self.base_url}/list/{self.list_id}/task"
        
        # Debug logging
        self.debug(f"🔍 DEBUG - Creating task: {task_data.get('name', 'Unknown')}")
        self.debug(f"🔍 DEBUG - API URL: {url}")
        self.debug(f"🔍 DEBUG - Headers: {self.headers}")
        self.debug(f"🔍 DEBUG - Task data keys: {list(task_data.keys())}")
        self.debug(f"🔍 DEBUG - Task data size: {len(str(task_data))} characters")
        if 'markdown_content' in task_data:
            self.debug(f"🔍 DEBUG - Markdown content length: {len(task_data['markdown_content'])} characters")
            self.debug(f"🔍 DEBUG - Markdown content preview: {task_data['markdown_content'][:100]}...")
        
        try:
            self.debug("🔍 DEBUG - Sending POST request...")
            response = requests.post(url, headers=self.headers, json=task_data)
            self.debug(f"🔍 DEBUG - Response status: {response.status_code}")
            self.debug(f"🔍 DEBUG - Response headers: {dict(response.headers)}")
            self.debug(f"🔍 DEBUG - Response text: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            self.debug(f"✅ DEBUG - Task created successfully with ID: {result.get('id')}")
            return result
        except requests.exceptions.RequestException as e:
            print(f"❌ ERROR creating task '{task_data.get('name', 'Unknown')}': {e}")
            if hasattr(e, 'response') and e.response:
                print(f"❌ ERROR - Response status: {e.response.status_code}")
                print(f"❌ ERROR - Response headers: {dict(e.response.headers)}")
                print(f"❌ ERROR - Response text: {e.response.text}")
                
                # Try to parse error response as JSON for more details
                try:
                    error_json = e.response.json()
                    print(f"❌ ERROR - Parsed error response: {error_json}")
                except:
                    print("❌ ERROR - Could not parse error response as JSON")
            return None
    
    def add_task_comment(self, task_id: str, comment_text: str) -> bool:
        """Add a comment to a task"""
        url = f"{self.base_url}/task/{task_id}/comment"
        comment_data = {
            "comment_text": comment_text
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=comment_data)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error adding comment to task {task_id}: {e}")
            return False
    
    def parse_jira_xml(self, xml_file: str, limit: Optional[int] = None) -> List[Dict]:
        """Parse JIRA XML export and extract task data"""
        print(f"Parsing XML file: {xml_file}")
        
        # Read and clean the XML file
        with open(xml_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove the problematic comment at the beginning
        content = re.sub(r'^.*?<rss', '<rss', content, flags=re.DOTALL)
        
        # Parse XML from cleaned content using lxml
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(content.encode('utf-8'), parser)
        
        # Build user mapping first so we can resolve names in comments
        self.build_user_mapping(root)
        
        # Find all items
        items = root.findall('.//item')
        print(f"Found {len(items)} items in XML")
        
        # Apply limit if specified
        if limit is not None:
            items = items[:limit]
            print(f"Limiting to first {len(items)} items")
        
        tasks = []
        
        for item in items:
            # Extract basic fields
            key_elem = item.find('key')
            key = key_elem.text if key_elem is not None else ''
            
            summary_elem = item.find('summary')
            summary = summary_elem.text if summary_elem is not None else ''
            
            description_elem = item.find('description')
            description = self.extract_html_content(description_elem) if description_elem is not None else ''
            
            status_elem = item.find('status')
            status = status_elem.text if status_elem is not None else ''
            
            priority_elem = item.find('priority')
            priority = priority_elem.text if priority_elem is not None else 'Medium'
            
            assignee_elem = item.find('assignee')
            assignee = assignee_elem.text if assignee_elem is not None else ''
            
            reporter_elem = item.find('reporter')
            reporter = reporter_elem.text if reporter_elem is not None else ''
            
            created_elem = item.find('created')
            created = self.parse_date(created_elem.text if created_elem is not None else None)
            
            updated_elem = item.find('updated')
            updated = self.parse_date(updated_elem.text if updated_elem is not None else None)
            
            due_elem = item.find('due')
            due_date = self.parse_date(due_elem.text if due_elem is not None and due_elem.text else None)
            
            # Extract project info
            project_elem = item.find('project')
            project_key = project_elem.get('key', '') if project_elem is not None else ''
            project_name = project_elem.text if project_elem is not None else ''
            
            # Extract comments
            comments = self.extract_comments(item)
            
            # Extract attachments
            attachments = self.extract_attachments(item)
            
            # Create task description with metadata
            full_description = self.create_task_description(description, created, assignee, reporter)
            
            # Create tags from project and other metadata
            tags = []
            if project_key:
                tags.append(project_key)
            # Note: Status is now mapped to ClickUp status field instead of tag
            # Note: Assignee is now mapped to custom field instead of tag
            
            # Map JIRA status to ClickUp status
            mapped_status = self.map_status(status)
            
            # Prepare task data
            task_data = {
                'jira_key': key,
                'name': f"[{key}] {summary}",
                'description': full_description,
                'priority': self.map_priority(priority),
                'tags': tags,
                'assignees': [],  # Will need to map JIRA users to ClickUp user IDs
                'status': mapped_status,
                'jira_status': status,  # Keep original for reference
                'created_date': created,
                'updated_date': updated,
                'due_date': due_date,
                'assignee': assignee,
                'reporter': reporter,
                'project': project_name,
                'comments': comments,
                'attachments': attachments
            }
            
            tasks.append(task_data)
        
        return tasks
    
    def convert_date_to_unix_ms(self, date_obj: Optional[datetime]) -> Optional[int]:
        """Convert datetime object to Unix timestamp in milliseconds"""
        if date_obj:
            return int(date_obj.timestamp() * 1000)
        return None
    
    def import_tasks(self, tasks: List[Dict], dry_run: bool = False) -> None:
        """Import tasks to ClickUp"""
        print(f"\n{'DRY RUN: ' if dry_run else ''}Starting import of {len(tasks)} tasks...")
        self.debug(f"🔍 DEBUG - Import method called with {len(tasks)} tasks, dry_run={dry_run}")
        
        for i, task in enumerate(tasks, 1):
            print(f"\n[{i}/{len(tasks)}] Processing task: {task['jira_key']} - {task['name'][:50]}...")
            self.debug(f"🔍 DEBUG - Raw task data: jira_key={task['jira_key']}, priority={task['priority']}, status={task['jira_status']}->{task['status']}, tags={task['tags']}")
            
            # Prepare ClickUp task data
            clickup_task = {
                "name": task['name'],
                "markdown_content": task['description'],
                "priority": task['priority'],
                "tags": task['tags']
            }
            
            # Add status if mapped
            if task['status']:
                clickup_task['status'] = task['status']
                self.debug(f"🔍 DEBUG - Added status: {task['jira_status']} -> {task['status']}")
            
            # Add due date if available
            if task['due_date']:
                clickup_task['due_date'] = self.convert_date_to_unix_ms(task['due_date'])
                self.debug(f"🔍 DEBUG - Added due date: {clickup_task['due_date']}")
            
            # Add custom fields
            custom_fields = self.create_custom_fields(task['assignee'])
            if custom_fields:
                clickup_task['custom_fields'] = custom_fields
                self.debug(f"🔍 DEBUG - Added custom fields: {custom_fields}")
            
            self.debug(f"🔍 DEBUG - Final ClickUp task data prepared: {clickup_task.keys()}")
            
            if dry_run:
                print(f"  Would create task: {json.dumps(clickup_task, indent=2, default=str)}")
                continue
            
            # Create the task
            created_task = self.create_clickup_task(clickup_task)
            
            if created_task:
                task_id = created_task.get('id')
                print(f"  ✓ Successfully created task with ID: {task_id}")
                
                # Store success info
                self.created_tasks.append({
                    'jira_key': task['jira_key'],
                    'clickup_id': task_id,
                    'name': task['name']
                })
                
                # Add individual comments if there are any
                if task['comments'] and len(task['comments']) > 0:
                    print(f"  Adding {len(task['comments'])} comments...")
                    for j, comment in enumerate(task['comments'], 1):
                        comment_text = f"Original comment by {comment['author']} ({comment['created']}):\n\n{comment['content']}"
                        if self.add_task_comment(task_id, comment_text):
                            print(f"    ✓ Added comment {j}")
                        else:
                            print(f"    ✗ Failed to add comment {j}")
                        time.sleep(0.5)  # Rate limiting
                
                # Add attachments if there are any
                if task['attachments'] and len(task['attachments']) > 0:
                    print(f"  Processing {len(task['attachments'])} attachments...")
                    for j, attachment in enumerate(task['attachments'], 1):
                        attachment_name = attachment['name']
                        attachment_id = attachment['id']
                        
                        # Download from JIRA
                        temp_file_path = self.download_jira_attachment(attachment_id, attachment_name)
                        if temp_file_path:
                            # Upload to ClickUp
                            if self.upload_clickup_attachment(task_id, temp_file_path, attachment_name):
                                print(f"    ✓ Added attachment {j}: {attachment_name}")
                            else:
                                print(f"    ✗ Failed to upload attachment {j}: {attachment_name}")
                            
                            # Clean up temporary file
                            try:
                                os.unlink(temp_file_path)
                            except:
                                pass
                        else:
                            print(f"    ✗ Failed to download attachment {j}: {attachment_name}")
                        
                        time.sleep(0.5)  # Rate limiting
                
            else:
                print(f"  ✗ Failed to create task")
                self.failed_tasks.append({
                    'jira_key': task['jira_key'],
                    'name': task['name'],
                    'error': 'Task creation failed'
                })
            
            # Rate limiting - ClickUp has rate limits
            time.sleep(1)
        
        # Print summary
        print(f"\n{'DRY RUN ' if dry_run else ''}IMPORT SUMMARY:")
        print(f"Total tasks processed: {len(tasks)}")
        if not dry_run:
            print(f"Successfully created: {len(self.created_tasks)}")
            print(f"Failed: {len(self.failed_tasks)}")
            
            if self.failed_tasks:
                print("\nFailed tasks:")
                for failed in self.failed_tasks:
                    print(f"  - {failed['jira_key']}: {failed['name']}")

def debug_print(message: str, verbose: bool) -> None:
    """Print debug message only if verbose mode is enabled"""
    if verbose:
        print(message)

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    parser = argparse.ArgumentParser(description='Import JIRA XML export to ClickUp')
    parser.add_argument('xml_file', nargs='?', help='Path to JIRA XML export file')
    parser.add_argument('--api-token', help='ClickUp API token (can also be set via CLICKUP_API_TOKEN env var)')
    parser.add_argument('--list-id', help='ClickUp List ID to import tasks to (can also be set via CLICKUP_LIST_ID env var)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be imported without actually creating tasks')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable detailed debugging output')
    parser.add_argument('--limit', type=int, help='Limit the number of tasks to import (useful for testing)')
    parser.add_argument('--list-custom-fields', action='store_true', help='List all custom fields in the ClickUp list (helps find field IDs)')
    parser.add_argument('--jira-base-url', help='JIRA base URL (e.g., https://umwerk.atlassian.net/)')
    parser.add_argument('--jira-api-token', help='JIRA API token for downloading attachments (can also be set via JIRA_API_TOKEN env var)')
    parser.add_argument('--jira-email', help='JIRA email address for basic auth (can also be set via JIRA_EMAIL env var)')
    
    args = parser.parse_args()
    
    # Get configuration from environment variables or command line arguments
    api_token = args.api_token or os.getenv('CLICKUP_API_TOKEN')
    list_id = args.list_id or os.getenv('CLICKUP_LIST_ID')
    xml_file = args.xml_file or os.getenv('JIRA_XML_FILE')
    jira_base_url = args.jira_base_url or os.getenv('JIRA_BASE_URL')
    jira_api_token = args.jira_api_token or os.getenv('JIRA_API_TOKEN')
    jira_email = args.jira_email or os.getenv('JIRA_EMAIL')
    
    # Debug logging
    debug_print("🔍 DEBUG - Loading environment variables from .env file...", args.verbose)
    debug_print("🔍 DEBUG - Configuration loaded:", args.verbose)
    debug_print(f"🔍 DEBUG - API Token: {'*' * 10}{api_token[-10:] if api_token and len(api_token) > 10 else 'None'}", args.verbose)
    debug_print(f"🔍 DEBUG - List ID: {list_id}", args.verbose)
    debug_print(f"🔍 DEBUG - XML File: {xml_file}", args.verbose)
    debug_print(f"🔍 DEBUG - JIRA Base URL: {jira_base_url}", args.verbose)
    debug_print(f"🔍 DEBUG - JIRA Email: {jira_email}", args.verbose)
    debug_print(f"🔍 DEBUG - Dry Run: {args.dry_run}", args.verbose)
    debug_print(f"🔍 DEBUG - Command line args: {vars(args)}", args.verbose)
    
    # Validate required parameters
    if not api_token:
        print("Error: ClickUp API token is required. Set CLICKUP_API_TOKEN environment variable or use --api-token")
        return 1
    
    if not list_id:
        print("Error: ClickUp List ID is required. Set CLICKUP_LIST_ID environment variable or use --list-id")
        return 1
    
    # XML file is only required if not just listing custom fields
    if not args.list_custom_fields:
        if not xml_file:
            print("Error: XML file path is required. Set JIRA_XML_FILE environment variable or provide as argument")
            return 1
        
        # Validate inputs
        if not os.path.exists(xml_file):
            print(f"Error: XML file '{xml_file}' not found")
            return 1
    
    # Create importer
    debug_print("🔍 DEBUG - Creating ClickUp importer...", args.verbose)
    importer = JiraToClickUpImporter(api_token, list_id, jira_base_url, jira_api_token, jira_email, args.verbose)
    debug_print(f"🔍 DEBUG - Importer created with headers: {importer.headers}", args.verbose)
    debug_print(f"🔍 DEBUG - Base URL: {importer.base_url}", args.verbose)
    debug_print(f"🔍 DEBUG - List ID: {importer.list_id}", args.verbose)
    
    # Handle custom fields listing
    if args.list_custom_fields:
        print("\n🔍 Fetching custom fields from ClickUp list...")
        importer.get_list_custom_fields()
        print("\n💡 To use a custom field:")
        print("   1. Copy the ID of the 'Jira Assignee' field from above")
        print("   2. Update the 'jira_assignee_field_id' in the code with that ID")
        print("   3. Re-run without --list-custom-fields")
        return 0
    
    try:
        # Parse JIRA XML
        tasks = importer.parse_jira_xml(xml_file, limit=args.limit)
        
        if not tasks:
            print("No tasks found in XML file")
            return 1
        
        # Import tasks
        importer.import_tasks(tasks, dry_run=args.dry_run)
        
        print("\nImport completed!")
        return 0
        
    except Exception as e:
        print(f"Error during import: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main()) 