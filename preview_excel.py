#!/usr/bin/env python3
"""
Preview Excel data to verify conversion
"""

import pandas as pd

def preview_excel_data(excel_file):
    """Preview the Excel data"""
    print(f"Reading Excel file: {excel_file}")
    
    # Read the Excel file
    df = pd.read_excel(excel_file)
    
    print(f"\nDataFrame shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    
    print("\nFirst 5 rows:")
    print(df.head())
    
    print("\nData types:")
    print(df.dtypes)
    
    print("\nSummary statistics:")
    print(f"- Total rows: {len(df)}")
    print(f"- Unique keys: {df['Key'].nunique()}")
    print(f"- Statuses: {df['Status'].value_counts().to_dict()}")
    print(f"- Priorities: {df['Priority'].value_counts().to_dict()}")

if __name__ == "__main__":
    excel_file = "jira_export.xlsx"
    preview_excel_data(excel_file) 