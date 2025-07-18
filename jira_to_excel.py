#!/usr/bin/env python3
"""
Jira XML to Excel Converter
Converts Jira XML export to Excel format with all relevant fields.
"""

import pandas as pd
import re
from datetime import datetime
import html
from lxml import etree

def clean_html(text):
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

def extract_html_content(element):
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

def html_to_markdown(html_content):
    """Convert HTML content to markdown format"""
    if not html_content:
        return ""
    
    # Convert common HTML tags to markdown
    content = html_content
    
    # Headers
    content = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1', content, flags=re.DOTALL)
    content = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', content, flags=re.DOTALL)
    content = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1', content, flags=re.DOTALL)
    content = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1', content, flags=re.DOTALL)
    content = re.sub(r'<h5[^>]*>(.*?)</h5>', r'##### \1', content, flags=re.DOTALL)
    content = re.sub(r'<h6[^>]*>(.*?)</h6>', r'###### \1', content, flags=re.DOTALL)
    
    # Bold and italic
    content = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', content, flags=re.DOTALL)
    content = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', content, flags=re.DOTALL)
    content = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', content, flags=re.DOTALL)
    content = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', content, flags=re.DOTALL)
    
    # Links
    content = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', content, flags=re.DOTALL)
    
    # Lists
    content = re.sub(r'<ul[^>]*>(.*?)</ul>', r'\1', content, flags=re.DOTALL)
    content = re.sub(r'<ol[^>]*>(.*?)</ol>', r'\1', content, flags=re.DOTALL)
    content = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1', content, flags=re.DOTALL)
    
    # Paragraphs and line breaks
    content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', content, flags=re.DOTALL)
    content = re.sub(r'<br[^>]*/?>', r'\n', content)
    content = re.sub(r'<div[^>]*>(.*?)</div>', r'\1\n', content, flags=re.DOTALL)
    
    # Blockquotes
    content = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'> \1', content, flags=re.DOTALL)
    
    # Code blocks
    content = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', content, flags=re.DOTALL)
    content = re.sub(r'<pre[^>]*>(.*?)</pre>', r'```\n\1\n```', content, flags=re.DOTALL)
    
    # Remove remaining HTML tags
    content = re.sub(r'<[^>]+>', '', content)
    
    # Decode HTML entities
    content = html.unescape(content)
    
    # Clean up extra whitespace and newlines
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    content = re.sub(r'^\s+|\s+$', '', content, flags=re.MULTILINE)
    
    return content.strip()

def html_to_plain_text(html_content):
    """Convert HTML content to clean plain text"""
    if not html_content:
        return ""
    
    # First convert to markdown for better structure
    markdown_content = html_to_markdown(html_content)
    
    # Remove markdown formatting for plain text
    content = markdown_content
    
    # Remove markdown links but keep the text
    content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)
    
    # Remove markdown formatting
    content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)  # Bold
    content = re.sub(r'\*([^*]+)\*', r'\1', content)      # Italic
    content = re.sub(r'`([^`]+)`', r'\1', content)        # Code
    content = re.sub(r'^#+\s+', '', content, flags=re.MULTILINE)  # Headers
    content = re.sub(r'^>\s+', '', content, flags=re.MULTILINE)   # Blockquotes
    content = re.sub(r'^- ', '', content, flags=re.MULTILINE)     # List items
    
    # Clean up extra whitespace
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    content = re.sub(r'^\s+|\s+$', '', content, flags=re.MULTILINE)
    
    return content.strip()

def parse_date(date_str):
    """Parse Jira date format to Python datetime"""
    if not date_str:
        return None
    try:
        # Jira format: "Wed, 9 Jul 2025 14:31:57 +0200"
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    except:
        return None

def extract_account_id(element):
    """Extract account ID from element attributes"""
    if element is not None:
        return element.get('accountid', '')
    return ''

def extract_comments(item):
    """Extract all comments from an item"""
    comments = []
    comment_elements = item.findall('.//comment')
    
    for comment_elem in comment_elements:
        comment_id = comment_elem.get('id', '')
        author = comment_elem.get('author', '')
        created = parse_date(comment_elem.get('created', ''))
        content = extract_html_content(comment_elem)
        
        comment_data = {
            'Comment ID': comment_id,
            'Comment Author': author,
            'Comment Created': created,
            'Comment Content': content
        }
        comments.append(comment_data)
    
    return comments

def create_combined_content(description, comments):
    """Create combined markdown and plain text content from description and comments"""
    markdown_parts = []
    plain_text_parts = []
    
    # Add description
    if description:
        markdown_desc = html_to_markdown(description)
        plain_desc = html_to_plain_text(description)
        
        markdown_parts.append(f"## Description\n\n{markdown_desc}")
        plain_text_parts.append(f"DESCRIPTION:\n{plain_desc}")
    
    # Add comments
    if comments:
        markdown_parts.append("## Comments")
        plain_text_parts.append("COMMENTS:")
        
        for i, comment in enumerate(comments, 1):
            author = comment['Comment Author']
            created = comment['Comment Created']
            content = comment['Comment Content']
            
            # Format date
            date_str = created.strftime('%Y-%m-%d %H:%M:%S') if isinstance(created, datetime) else str(created)
            
            # Convert to markdown
            markdown_content = html_to_markdown(content)
            plain_content = html_to_plain_text(content)
            
            markdown_parts.append(f"\n### Comment {i} - {author} ({date_str})\n\n{markdown_content}")
            plain_text_parts.append(f"\nComment {i} - {author} ({date_str}):\n{plain_content}")
    
    return '\n\n'.join(markdown_parts), '\n\n'.join(plain_text_parts)

def convert_jira_xml_to_excel(xml_file, excel_file):
    """Convert Jira XML export to Excel"""
    
    print(f"Parsing XML file: {xml_file}")
    
    # Read the file and clean it up
    with open(xml_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove the problematic comment at the beginning
    content = re.sub(r'^.*?<rss', '<rss', content, flags=re.DOTALL)
    
    # Parse XML from cleaned content using lxml
    parser = etree.XMLParser(recover=True)  # This makes it more tolerant of errors
    root = etree.fromstring(content.encode('utf-8'), parser)
    
    # Find all items
    items = root.findall('.//item')
    print(f"Found {len(items)} items")
    
    # Prepare data for Excel
    data = []
    
    for item in items:
        # Extract all fields
        key_elem = item.find('key')
        key = key_elem.text if key_elem is not None else ''
        key_id = key_elem.get('id', '') if key_elem is not None else ''
        
        summary_elem = item.find('summary')
        summary = summary_elem.text if summary_elem is not None else ''
        
        description_elem = item.find('description')
        description = extract_html_content(description_elem) if description_elem is not None else ''
        
        status_elem = item.find('status')
        status = status_elem.text if status_elem is not None else ''
        status_id = status_elem.get('id', '') if status_elem is not None else ''
        
        priority_elem = item.find('priority')
        priority = priority_elem.text if priority_elem is not None else ''
        priority_id = priority_elem.get('id', '') if priority_elem is not None else ''
        
        assignee_elem = item.find('assignee')
        assignee = assignee_elem.text if assignee_elem is not None else ''
        assignee_id = extract_account_id(assignee_elem)
        
        reporter_elem = item.find('reporter')
        reporter = reporter_elem.text if reporter_elem is not None else ''
        reporter_id = extract_account_id(reporter_elem)
        
        created_elem = item.find('created')
        created = parse_date(created_elem.text if created_elem is not None else None)
        
        updated_elem = item.find('updated')
        updated = parse_date(updated_elem.text if updated_elem is not None else None)
        
        # Extract comments
        comments = extract_comments(item)
        
        # Create combined content
        markdown_content, plain_text_content = create_combined_content(description, comments)
        
        # Create row data
        row = {
            'Key': key,
            'Key ID': key_id,
            'Summary': summary,
            'Description': description,
            'Status': status,
            'Status ID': status_id,
            'Priority': priority,
            'Priority ID': priority_id,
            'Assignee': assignee,
            'Assignee ID': assignee_id,
            'Reporter': reporter,
            'Reporter ID': reporter_id,
            'Created': created,
            'Updated': updated,
            'Comment Count': len(comments),
            'Combined Content (Markdown)': markdown_content,
            'Combined Content (Plain Text)': plain_text_content
        }
        
        # Add comment data if there are comments
        if comments:
            # Combine all comments into one field for the main sheet
            all_comments = []
            for i, comment in enumerate(comments, 1):
                comment_text = f"Comment {i} ({comment['Comment Author']} - {comment['Comment Created']}): {comment['Comment Content']}"
                all_comments.append(comment_text)
            
            row['All Comments'] = '\n\n'.join(all_comments)
        else:
            row['All Comments'] = ''
        
        data.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Convert datetime columns to string for Excel
    if 'Created' in df.columns:
        # Convert datetime objects to string format
        df['Created'] = df['Created'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if isinstance(x, datetime) else x)
    
    if 'Updated' in df.columns:
        # Convert datetime objects to string format
        df['Updated'] = df['Updated'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if isinstance(x, datetime) else x)
    
    # Write to Excel
    print(f"Writing {len(df)} rows to Excel file: {excel_file}")
    
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        # Main sheet with all issues
        df.to_excel(writer, sheet_name='Jira Issues', index=False)
        
        # Auto-adjust column widths for main sheet
        worksheet = writer.sheets['Jira Issues']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Create a separate sheet for detailed comments
        all_comments_data = []
        for item in items:
            key_elem = item.find('key')
            key = key_elem.text if key_elem is not None else ''
            
            comments = extract_comments(item)
            for comment in comments:
                comment_row = {
                    'Issue Key': key,
                    'Comment ID': comment['Comment ID'],
                    'Comment Author': comment['Comment Author'],
                    'Comment Created': comment['Comment Created'],
                    'Comment Content': comment['Comment Content']
                }
                all_comments_data.append(comment_row)
        
        if all_comments_data:
            comments_df = pd.DataFrame(all_comments_data)
            # Convert datetime for comments
            comments_df['Comment Created'] = comments_df['Comment Created'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if isinstance(x, datetime) else x
            )
            comments_df.to_excel(writer, sheet_name='Comments', index=False)
            
            # Auto-adjust column widths for comments sheet
            comments_worksheet = writer.sheets['Comments']
            for column in comments_worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                comments_worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"Successfully converted {len(df)} items to Excel!")
    print(f"Excel file saved as: {excel_file}")
    
    # Print summary
    print("\nSummary:")
    print(f"- Total issues: {len(df)}")
    print(f"- Total comments: {len(all_comments_data)}")
    print(f"- Issues with comments: {len(df[df['Comment Count'] > 0])}")
    print(f"- Statuses: {df['Status'].value_counts().to_dict()}")
    print(f"- Priorities: {df['Priority'].value_counts().to_dict()}")
    print(f"- Assignees: {df['Assignee'].value_counts().to_dict()}")

if __name__ == "__main__":
    xml_file = "sisr-export.xml"
    excel_file = "jira_export.xlsx"
    
    try:
        convert_jira_xml_to_excel(xml_file, excel_file)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc() 