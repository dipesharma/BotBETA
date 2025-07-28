# db_utils.py

import pyodbc
import logging
import time

def execute_sql_query(query, cursor):
    try:
        logging.info(f"db_utils:execute_sql_query: Executing query (truncated): {query[:200]}...")
 
        start_time = time.time() # Start timer
 
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        # Fetch all rows and zip with column names to create list of dicts
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
 
        end_time = time.time() # End timer
        duration = end_time - start_time
 
        # Add the new log message with the duration
        logging.info(f"    [DB Query] Execution took {duration:.4f}s. Fetched {len(results)} rows.")
 
        return results
    except pyodbc.Error as e:
        # ... error handling ...
        logging.error(f"db_utils:execute_sql_query: SQL execution failed: {str(e)}", exc_info=True)
        # Re-raise the exception so the caller can handle it (e.g., return an error message)
        raise
    except Exception as e:
        logging.error(f"db_utils:execute_sql_query: An unexpected error occurred during SQL execution: {e}", exc_info=True)
        raise # Re-raise unexpected errors as well

