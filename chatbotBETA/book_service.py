# book_service.py

import logging
import re
import pyodbc
from deepseek1 import get_sql_from_deepseek, filter_books_with_deepseek
from sql_utils import clean_sql
from db_utils import execute_sql_query # Assuming db_utils has execute_sql_query
from services import AIService
import time

class BookRecommendationService:
    """Service to handle book recommendation logic"""

    @staticmethod
    def recommend_books(user_query, db_cursor): # Keep db_cursor as parameter as per your last file
        """
        Generates book recommendations based on user query using a provided database cursor.
        """
        if not db_cursor or not isinstance(db_cursor, pyodbc.Cursor):
            logging.error("BookRecommendationService:recommend_books: Invalid or missing database cursor provided at the start.")
            return "Our recommendation engine is taking a coffee break. Please try again shortly!"

        loading_line = "" # Initialize loading line
        final_books = []

        # --- PHASE 1: Get Book Data (Your original, reliable logic) ---
        try:
            logging.info(f"BookRecommendationService:recommend_books: Getting SQL query from DeepSeek for: {user_query}")
            # get_sql_from_deepseek now returns (sql_text, loading_line, token_used)
            try:
                # UNPACK HERE ACCORDING TO DEEPSEEK1.PY'S RETURN SIGNATURE
                sql_text_raw, deepseek_loading_line, token_used = get_sql_from_deepseek(user_query)
                loading_line = deepseek_loading_line if deepseek_loading_line else "" # Use the loading line directly
        
                logging.info(f"BookRecommendationService:recommend_books: Received SQL and loading line from DeepSeek.")
            except Exception as deepseek_sql_error:
                logging.error(f"BookRecommendationService:recommend_books: Error getting SQL from DeepSeek: {deepseek_sql_error}", exc_info=True)
                return f"Hmm, I got a bit tangled trying to understand your request. Mind rephrasing it for me?"

            logging.info(f"BookRecommendationService:recommend_books: Raw SQL from DeepSeek: {sql_text_raw}")
            logging.info(f"BookRecommendationService:recommend_books: DeepSeek loading line: {loading_line}")

            # Clean the SQL query (sql_text_raw already stripped of loading_line by deepseek1.py)
            logging.info("BookRecommendationService:recommend_books: Cleaning SQL query...")
            clean_query = clean_sql(sql_text_raw) # Pass the raw SQL text
            logging.info(f"BookRecommendationService:recommend_books: Cleaned SQL query: {clean_query}")

            # Execute the SQL query using the provided cursor
            logging.info("BookRecommendationService:recommend_books: Executing SQL query...")
            try:
                # Ensure db_cursor is still valid immediately before execution
                if not db_cursor or not isinstance(db_cursor, pyodbc.Cursor):
                        logging.error("BookRecommendationService:recommend_books: Database cursor became invalid before execution.")
                        return "Oops! I lost my connection to the book vault. Let’s give it another go in a moment!"

                db_results = execute_sql_query(clean_query, db_cursor)
                logging.info(f"BookRecommendationService:recommend_books: Retrieved {len(db_results)} books from database.")
            except Exception as db_error:
                logging.error(f"BookRecommendationService:recommend_books: Error executing SQL query: {db_error}", exc_info=True)
                return f"{loading_line}\n\nStill fetching your books... but I ran into a snag searching the shelf. Try again soon?"


            if not db_results:
                return f"{loading_line}\n\nWe looked high and low but couldn’t find any matching books. Try tweaking your request?"

            # Filter results using DeepSeek
            logging.info("BookRecommendationService:recommend_books: Filtering results with DeepSeek...")
            try:
                selected_indices = filter_books_with_deepseek(user_query, db_results)
                final_books = [db_results[i] for i in selected_indices if i < len(db_results)] # Add bounds check
                logging.info(f"BookRecommendationService:recommend_books: Final recommended books after filtering: {len(final_books)}")
            except Exception as filter_error:
                logging.error(f"BookRecommendationService:recommend_books: Error filtering books with DeepSeek: {filter_error}", exc_info=True)
                # Fallback: If filtering fails, use all initially retrieved books (up to 50)
                logging.warning("BookRecommendationService:recommend_books: Filtering failed, falling back to all retrieved books (up to 50).")
                final_books = db_results[:15] # Use initial results if filtering fails

            if not final_books:
                # This case only happens if db_results was not empty, but filtering (or fallback) resulted in no books.
                # This is unlikely with the fallback, but good to keep.
                return f"{loading_line}\n\nI fetched some titles, but none seemed quite right. Try a slightly different request?"

        except Exception as e:
            logging.error(f"BookRecommendationService:recommend_books: An unexpected error occurred during book recommendation process: {e}", exc_info=True)
            return f"Something went off-script while hunting down books for you. Let’s try that again soon!"

        # --- PHASE 2: Generate Conversational Response (Reverted to reliable two-step process) ---
        try:
            # Step 2a: Generate the conversational opening with a dedicated AI call
            conversational_prompt = f"""
            You are Vidya, a friendly and warm bookstore assistant. A user asked: "{user_query}".
            Your task is to write a short, warm, and conversational opening paragraph (1-2 sentences) that directly addresses the user's question or context. For example, if they asked if a book is good for a child, confirm that it is and briefly explain why.
            Do NOT list any books. Just write the opening paragraph.IMPORTANT: Your entire response must be plain text. Do NOT use any Markdown formatting, such as asterisks for italics or bold, or surrounding quotes.
            """
            start_time = time.time() # Start timer
            conversational_opening = AIService.query_deepseek([{"role": "user", "content": conversational_prompt}], temperature=0.7)
            end_time = time.time() # End timer
            duration = end_time - start_time
            # Add a new log message with the duration
            logging.info(f"    [AI Conversation] AI call took {duration:.4f}s") 

        except Exception as e:
            logging.error(f"BookRecommendationService:recommend_books: Error generating conversational opening: {e}")
            # If the conversational AI call fails, we create a safe, default opening.
            conversational_opening = "Here are some books I found for you:"

        # Step 2b: Manually format the book list using your original, reliable logic
        formatted_books = []
        for i, book in enumerate(final_books, 1):
            title = book.get('Product_Title', 'N/A')
            author = book.get('AuthorName1', 'N/A')

            price_value = book.get('Product_DiscountedPrice')
            price = "N/A"
            if price_value is not None:
                try:
                    price = f"₹{float(price_value):.2f}"
                except (ValueError, TypeError):
                    logging.warning(f"BookRecommendationService:recommend_books: Could not convert price value '{price_value}' to float for book: {title}")
                    price = "N/A"

            title_url_raw = book.get('Product_TitleURl')
            isbn_raw = book.get('ISBN13')
            title_url = str(title_url_raw).strip() if title_url_raw else ''
            isbn = str(isbn_raw).strip() if isbn_raw else ''

            if title_url and isbn:
                link = f"www.bookswagon.com/book/{title_url}/{isbn}"
            else:
                link = "Link not available"

            formatted_books.append(f"\n{i}. Title: {title}\n   Author: {author}\n   Price: {price}\n   Link: {link}")

        # Step 2c: Combine all parts into the final response
        final_response_parts = []
        if loading_line:
            final_response_parts.append(loading_line)

        final_response_parts.append(conversational_opening)
        final_response_parts.extend(formatted_books)

        return "\n".join(final_response_parts)
 