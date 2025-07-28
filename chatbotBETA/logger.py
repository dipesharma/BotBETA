import os
import pandas as pd
from datetime import datetime
import json
import logging  # Import logging

def log_to_excel(user_query, sql_query, num_fetched, num_filtered, final_books, token_used, deepseek_sql_payload=None, deepseek_filter_payload=None):
    """
    Logs book query information to an Excel file.

    Args:
        user_query (str): The user's original query.
        sql_query (str): The SQL query executed.
        num_fetched (int): Number of books fetched from the database.
        num_filtered (int): Number of books after filtering.
        final_books (list): List of book dictionaries after filtering.
        token_used (int): Number of tokens used by DeepSeek.
        deepseek_sql_payload (dict, optional): The payload sent to DeepSeek for SQL generation. Defaults to None.
        deepseek_filter_payload (dict, optional): The payload sent to DeepSeek for filtering. Defaults to None.
    """
    log_file = "book_query_log.xlsx"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Extract top book titles, handling potential errors
    top_book_titles = []
    if final_books:  # Check if final_books is not empty
        try:
            top_book_titles = "; ".join([book.get("Product_Title", "N/A") for book in final_books[:3]])
        except Exception as e:
            logging.error(f"logger.py:log_to_excel: Error extracting top book titles: {e}", exc_info=True)
            top_book_titles = "Error extracting titles"  # Set an error message

    # Prepare the log entry.  Include the DeepSeek payloads
    log_entry = {
        "Timestamp": timestamp,
        "User Query": user_query,
        "SQL Query": sql_query,
        "Books Fetched": num_fetched,
        "Books After Filter": num_filtered,
        "Top Book Titles": top_book_titles,
        "DeepSeek Tokens Used": token_used,
        "DeepSeek SQL Request": json.dumps(deepseek_sql_payload) if deepseek_sql_payload else "N/A",
        "DeepSeek Filter Request": json.dumps(deepseek_filter_payload) if deepseek_filter_payload else "N/A",
    }

    # Load existing log or create new
    try:
        if os.path.exists(log_file):
            df = pd.read_excel(log_file)
            df = pd.concat([df, pd.DataFrame([log_entry])], ignore_index=True)
        else:
            df = pd.DataFrame([log_entry])
    except Exception as e:
        logging.error(f"logger.py:log_to_excel: Error handling Excel file: {e}", exc_info=True)
        print(f"Error writing to log file: {e}")  # print to standard error as well
        return  # IMPORTANT: Exit the function if there's an error with the Excel file.

    # Save back to Excel
    try:
        df.to_excel(log_file, index=False)
        logging.info(f"logger.py:log_to_excel: Successfully wrote to log file: {log_file}")
    except Exception as e:
        logging.error(f"logger.py:log_to_excel: Error saving to Excel file: {e}", exc_info=True)
        print(f"Error saving log file: {e}") # print to standard error.
        return # Exit if saving fails.