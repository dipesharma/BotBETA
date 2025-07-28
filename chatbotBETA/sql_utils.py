import re
 
def extract_sql_query(text):
    # Try to extract just the SQL statement
    sql_match = re.search(r'SELECT\s+.*?;', text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(0)
   
    # If no SQL found, remove any markdown code blocks
    cleaned = re.sub(r'```sql|```', '', text).strip()
    return cleaned
 
# --- Clean SQL to avoid % errors, quotes etc.
def clean_sql(sql_text):
    # First extract the actual SQL query
    sql_text = extract_sql_query(sql_text)
   
    # Clean up whitespace
    sql_text = re.sub(r"\s+", " ", sql_text).strip()
 
    # Fix LIKE patterns with multiple wildcards
    def fix_like_pattern(match):
        column = match.group(1)
        pattern = match.group(2)
       
        # If there are multiple terms separated by %
        if '%' in pattern:
            terms = [t for t in pattern.split('%') if t]
            if len(terms) > 1:
                conditions = [f"{column} LIKE '%{term}%'" for term in terms]
                return '(' + ' AND '.join(conditions) + ')'
       
        # If no internal %, return as is
        return f"{column} LIKE '%{pattern}%'"
   
    # Apply the pattern fix
    sql_text = re.sub(r'(\w+)\s+LIKE\s+\'%([^\']+?)%\'', fix_like_pattern, sql_text)
   
    # Fix unbalanced quotes
    if sql_text.count("'") % 2 != 0:
        sql_text = sql_text.rstrip(";'") + "'"
        if not sql_text.endswith(";"):
            sql_text += ";"
   
    # Ensure the SQL ends with a semicolon
    if not sql_text.endswith(";"):
        sql_text += ";"
   
    return sql_text
 