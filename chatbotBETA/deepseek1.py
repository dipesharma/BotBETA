import requests
import re
import json
import logging
from config import Config
import time
# Assuming Config is correctly set up as per your project
api_key = Config.DEEPSEEK_API_KEY
model = Config.DEEPSEEK_MODEL
api_url = Config.DEEPSEEK_API_URL

# --- Configure DeepSeek specific logging ---
deepseek_logger = logging.getLogger('deepseek_activity')
deepseek_logger.setLevel(logging.INFO)

if not any(isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith('requests.log') for handler in deepseek_logger.handlers):
    try:
        deepseek_handler = logging.FileHandler('requests.log')
        deepseek_formatter = logging.Formatter('%(filename)s:%(funcName)s: %(message)s')
        deepseek_handler.setFormatter(deepseek_formatter)
        deepseek_logger.addHandler(deepseek_handler)
        logging.info("deepseek1.py:Logging Setup: DeepSeek activity logger configured successfully.")
    except Exception as e:
        logging.error(f"deepseek1.py:Logging Setup: Failed to configure DeepSeek activity logger: {e}")
else:
    logging.info("deepseek1.py:Logging Setup: DeepSeek activity logger already configured.")


# --- SQL Query Cache ---
# Using a simple dictionary as an in-memory cache
sql_cache = {}
# Define a maximum cache size to prevent excessive memory usage
MAX_CACHE_SIZE = 1000 # You can adjust this value

# --- Book Filter Cache  ---
# Caches the results of the AI-powered book filtering
filter_cache = {}
# Using the same max size, but you can adjust if needed
MAX_FILTER_CACHE_SIZE = 1000


def get_sql_from_deepseek(user_query):
    """
    Generates a SQL query and a loading line based on user query using DeepSeek API.
    Implements in-memory caching for SQL queries.

    Args:
        user_query (str): The user's request.

    Returns:
        tuple: (sql_text, loading_line, token_used)
        sql_text (str): The generated SQL query.
        loading_line (str): An optional loading message from the AI.
        token_used (int): Number of tokens used (0 if from cache).
    """
    start_time = time.time()
    # Check if the query is in cache
    if user_query in sql_cache:
        cached_sql, cached_loading_line = sql_cache[user_query]
        deepseek_logger.info(f"DeepSeek:get_sql_from_deepseek: Cache hit for user query: '{user_query}'.")
        # Return 0 tokens used for cache hits
        return cached_sql, cached_loading_line, 0

    prompt = f"""
You are an expert SQL assistant for a book recommendation system.
Generate a SQL Server query using the table: `Table_ProductSearchNewSearch`.

**Key Constraints for SQL Generation:**
- **Crucial Rule for Accuracy: You MUST correct obvious spelling errors in user queries before generating the SQL.** For example, if a user asks for 'ancient rone', you must recognize this as a typo for 'ancient rome' and generate the query using the corrected term (e.g., `WHERE Product_Title LIKE '%ancient%rome%'`). Failing to correct typos will lead to no results and a bad user experience.
- **Always** include `Product_Title`, `AuthorName1`, `Category_Name`, `Product_DiscountedPrice`, `Product_TitleURl`, `ISBN13` in the `SELECT` clause.
- **Always** use `TOP 15` in the `SELECT` statement (e.g., `SELECT TOP 15 ...`).
- **Always** use `LIKE '%value%'` for partial string matches (e.g., `WHERE Product_Title LIKE '%meditation%'`).
- **Combine conditions with AND** for semantic relevance (e.g., "meditation books by specific author" -> `WHERE Product_Title LIKE '%meditation%' AND AuthorName1 LIKE '%author%'`).
- **Only use OR** within a single concept group (e.g., `(Product_Title LIKE '%Sci-Fi%' OR Product_Title LIKE '%Science Fiction%')`).
- If the user asks for multiple distinct criteria that are not related, combine them with AND.
- **Exclude** explicit keywords like "download" or "PDF" from your search terms.
- When a user asks for books similar to a specific title, suggest comparable options and exclude the mentioned book from the results.
- When suggesting books, prioritize top-quality, trending, or best-selling titles relevant to the category. For "bestsellers" or "top-selling" queries, *do not use WHERE clauses for ranking*; instead, rely solely on `ORDER BY Ranking ASC`.
- Smartly infer recency for queries like "recent" or "last 3 years" and emphasize current relevance over strict release dates, excluding older books unless they remain highly significant.
- Ignore specific keywords that refer to the platform or company name (e.g., 'bookswagon') when generating search criteria for book titles or author names.
- If the user specifies a language (e.g., "in Hindi", "English books"), use this information to filter results by the 'Language' column (e.g., WHERE Language = 'Hindi').
- **Always filter by availability if not explicitly contradicted**: Include `AND Availability != 'Out Of Stock'` in the `WHERE` clause unless the user specifically asks for unavailable books.
- If the user explicitly mentions a publisher (e.g., “books by Penguin”, “titles from HarperCollins”,"books from Double 9 Books"), filter using PublisherName LIKE '%<name>%' with Language = 'English', TOP 15, and ORDER BY Ranking ASC; otherwise, ignore the publisher
- If the user asks for new, recent, or latest books, fetch TOP 15 ordered by Date_Created DESC (latest year first), and ignore Date_Created unless freshness is clearly requested.
- If the user asks about discounts in percentage (e.g., “30% off”, “books with 50% discount”), filter using Product_discount >= <percentage>, fetch from relevant table with TOP 15, and ignore Product_discount unless discount percentage is clearly mentioned.
- If the user asks for books related to Award Winning, Box Sets, International Bestseller, or Top New Arrivals, fetch from `Table_TopBooksData` where `TopBookType` LIKE '%<type>%', use `Product_ActualPrice` for price, `AuthorName1` for author, and construct links using `Product_TitleURl` and `ISBN13`; ignore this logic unless one of these phrases is clearly mentioned. Do not use `Category_Name` in this specific category.
- For timeline queries ("recent", "last 3 years", "published on 1998"), infer recency or specific year. Use `PublicationDate` from `Table_ProductSearchNewSearch`. **To extract the year, use `TRY_CONVERT(DATE, PublicationDate, <style_code>)` or `YEAR(TRY_CONVERT(DATE, PublicationDate, <style_code>))` and try common SQL Server date style codes (e.g., 101, 103, 106, 120, etc.) to robustly convert the string to a date before extracting the year.** Prioritize `PublicationDate DESC` for recency or filter by `YEAR(TRY_CONVERT(DATE, PublicationDate, <style_code>)) = <year>` for specific years.
- **For multi-word searches in a title, you MUST separate each keyword with the SQL wildcard character `%`**. For example, if the user asks for "Harrison principles", the correct clause is `WHERE Product_Title LIKE '%Harrison%principles%'`, NOT `WHERE Product_Title LIKE '%Harrison principles%'`. This ensures the search isflexible and finds titles with variations like "Harrison's Principles of Internal Medicine".
- **Handle author initials with precision.** If a user searches for an author with initials typed without dots (e.g., "HC Verma", "JRR Tolkien"), you MUST reformat them by inserting a dot `.` between each initial letter in the `LIKE` clause. For example, a search for "HC Verma" should generate a clause like `WHERE AuthorName1 LIKE '%H.C%Verma%'`. This ensures you find authors formatted as 'H.C. Verma' or 'H.C Verma' without incorrectly matching other names. 

**Crucial Update for "New Arrivals/Latest Books":**
- **If the user explicitly asks for "new arrivals", "new books", "latest books", or similar phrases emphasizing recent additions, generate the query from `Table_TopBooksData` where `TopBookType` is 'Top New Arrivals' (e.g., `WHERE TopBookType = 'Top New Arrivals'`). For these queries, ensure `Product_ActualPrice` is used for price, `AuthorName1` for author, and construct links using `Product_TitleURl` and `ISBN13`. Do NOT use `Category_Name` and Date_Created for these specific queries.**

**Handling Categories, Topics, and Price Points:**
- If the user specifies a genre, category, or topic (e.g., "Indian mythology", "science fiction", "history"), prioritize filtering using `Category_Name LIKE '%<category>%'`.
- **Crucial Rule:** If a user specifies a category AND a related topic (e.g., "science fiction books about space exploration"), you MUST combine them with an `OR` to broaden the search. The query should look for books that are either in the category OR match the topic in the title. For example: `WHERE (Category_Name LIKE '%Science Fiction%' OR Product_Title LIKE '%space%exploration%')`. Using `AND` for this is too restrictive and will return poor results.
- If the user requests books "under X rupees" or "less than X price", filter using `Product_DiscountedPrice <= X` (e.g., `WHERE Product_DiscountedPrice <= 500`). Use `Product_DiscountedPrice` as the primary price filter.

**Enhanced Rule for Travel and Location-Based Queries:** - **If the user asks for books related to travel, exploration, or a specific geographic location/city (e.g., "books for Monaco travel", "exploring Paris", "guide to Rome"), prioritize `Category_Name LIKE '%Travel%'` or `Category_Name LIKE '%Guides%'` AND `Product_Title LIKE '%<location>%'` or `Product_Title LIKE '%<location> guide%'`. 
**Strict Output Format:**
Return ONLY the SQL query. Do NOT include any explanations, comments, or surrounding text (like markdown backticks).
Optionally, you can include a simple, short loading message at the very end of the response, in this exact format:
`loading_line: "Searching for books on [topic]..."`
If no specific topic can be inferred for the loading line, omit it.

**IMPROVED RULES for General and Vague Queries (Semantic Intent & Moods):** 
- **For mood-based or contextual queries (e.g., "it's been raining heavily, suggest me some books", "books for a cozy evening", "something to read on a relaxing Sunday", "uplifting reads", "books to cheer me up"), infer categories or themes that match the mood.**     
* **Rainy/Cozy/Relaxing:** Suggest `Category_Name LIKE '%Fiction%' OR Category_Name LIKE '%Mystery%' OR Category_Name LIKE '%Thriller%' OR Category_Name LIKE '%Romance%' OR Category_Name LIKE '%Fantasy%' OR Product_Title LIKE '%cozy%' OR Product_Title LIKE '%comfort%' OR Product_Title LIKE '%relax%'`.     
* **Uplifting/Cheer me up:** Suggest `Category_Name LIKE '%Self-Help%' OR Category_Name LIKE '%Inspiration%' OR Product_Title LIKE '%happiness%' OR Product_Title LIKE '%positivity%' OR Product_Title LIKE '%motivational%'`.     
* **General recommendations based on broad context (e.g., "suggest me books" without specific keywords):** Prioritize bestsellers by `ORDER BY Ranking ASC` or `TOP 15` from common popular categories such as `Fiction`, `Biographies`, `History`, `Self-Help`. If no other filter applies, just use `ORDER BY Ranking ASC`. 
- **For relationship advice/self-improvement queries (e.g., "how to keep your girl happy", "books on communication in relationships", "improving my marriage"), focus on relevant non-fiction categories and keywords.**     
* Suggest `Category_Name LIKE '%Self-Help%' OR Category_Name LIKE '%Relationships%' OR Category_Name LIKE '%Psychology%' OR Product_Title LIKE '%relationship%' OR Product_Title LIKE '%communication%' OR Product_Title LIKE '%marriage%' OR Product_Title LIKE '%happiness%' OR Product_Title LIKE '%love%'`. 
- **If the query contains seemingly random words or expressions (e.g., "purple hippos flying", "random stuff to read"), and no logical category or title match can be made, generate a default query for popular fiction:**     
* `SELECT TOP 15 Product_Title, AuthorName1, Category_Name, Product_DiscountedPrice, Product_TitleURl, ISBN13 FROM Table_ProductSearchNewSearch WHERE Category_Name LIKE '%Fiction%' AND Availability = 'Available' ORDER BY Ranking ASC;`     
* If no categories are mentioned or inferred, default to just `ORDER BY Ranking ASC`.

**NEW RULE for Multiple Publishers and Specific/Default Counts:** 
- **If the user explicitly mentions *multiple* publishers (e.g., "double 9 and penguin publishers", "HarperCollins or Random House"), generate a single query that combines the publishers using `OR` in the `PublisherName LIKE` clause. Use the *specified quantity* in the `TOP` clause if provided (e.g., "give me 5 titles" should result in `TOP 5`). If no quantity is specified, default to `TOP 15` for the combined results. Always include `Language = 'English'`, `AND Availability = 'Available'`, and `ORDER BY Ranking ASC` for publisher queries.**     
    * **Example with quantity:** `SELECT TOP <quantity> Product_Title, AuthorName1, Category_Name, Product_DiscountedPrice, Product_TitleURl, ISBN13 FROM Table_ProductSearchNewSearch WHERE (PublisherName LIKE '%<publisher1>%' OR PublisherName LIKE '%<publisher2>%') AND Language = 'English' AND Availability = 'Available' ORDER BY Ranking ASC;`     
    * **Example without quantity (defaults to TOP 15):** `SELECT TOP 15 Product_Title, AuthorName1, Category_Name, Product_DiscountedPrice, Product_TitleURl, ISBN13 FROM Table_ProductSearchNewSearch WHERE (PublisherName LIKE '%Double 9 Books%' OR PublisherName LIKE '%Harper Collins%') AND Language = 'English' AND Availability = 'Available' ORDER BY Ranking ASC;`
 

Example valid output:
SELECT TOP 15 Product_Title, AuthorName1, Category_Name, Product_SalePrice, Product_TitleURl, ISBN13 FROM Table_ProductSearchNewSearch WHERE Product_Title LIKE '%science fiction%' Order By Ranking ASC; loading_line: "Finding amazing science fiction titles..."

Example valid output (no loading line):
SELECT TOP 15 Product_Title, AuthorName1, Category_Name, Product_SalePrice, Product_TitleURl, ISBN13 FROM Table_ProductSearchNewSearch WHERE AuthorName1 LIKE '%Agatha Christie%' Order By Ranking ASC;
When printing output do not print loading line even though I asked above
"""
    messages = [{"role": "user", "content": prompt.strip() + f"\nUser Query: {user_query}"}]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
        "max_tokens": 500
    }

    #deepseek_logger.info(f"DeepSeek:get_sql_from_deepseek: Sending SQL generation query to DeepSeek. User Query: '{user_query}', Payload: {json.dumps(payload)}")

    try:
        start_time = time.time() # Start timer
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        end_time = time.time() # End timer
        duration = end_time - start_time
        # Add a new log message with the duration
        deepseek_logger.info(f"    [SQL Generation] AI call took {duration:.4f}s")
 
    except requests.exceptions.Timeout:
        logging.error("DeepSeek API call timed out in get_sql_from_deepseek.")
        deepseek_logger.error(f"DeepSeek:get_sql_from_deepseek: API call timed out for user query: '{user_query}'.")
        raise Exception("DeepSeek API did not respond in time for SQL generation.")
    except requests.exceptions.RequestException as e:
        logging.error(f"DeepSeek API request failed in get_sql_from_deepseek: {e}", exc_info=True)
        deepseek_logger.error(f"DeepSeek:get_sql_from_deepseek: API request failed for user query: '{user_query}'. Error: {e}")
        raise Exception(f"Failed to communicate with DeepSeek API for SQL generation: {e}")

    response_data = response.json()
    full_response_content = response_data['choices'][0]['message']['content'].strip()
    token_used = response_data.get('usage', {}).get('total_tokens', 0)

    #deepseek_logger.info(f"DeepSeek:get_sql_from_deepseek: Received raw response from DeepSeek for SQL generation. Response: {full_response_content}, Tokens Used: {token_used}")

    loading_line = None
    sql_text = full_response_content

    loading_line_match = re.search(r'loading_line:\s*"(.*?)"', full_response_content, re.DOTALL)
    if loading_line_match:
        loading_line = loading_line_match.group(1).strip()
        sql_text = re.sub(r'loading_line:\s*".*?"', '', full_response_content, flags=re.DOTALL).strip()
        logging.info(f"DeepSeek:get_sql_from_deepseek: Extracted loading line: {loading_line}")

    sql_text = re.sub(r'```sql|```', '', sql_text).strip()
    
    if not re.match(r'SELECT\s+TOP\s+\d+\s+.*?FROM\s+(?:Table_ProductSearchNewSearch|Table_TopBooksData)', sql_text, re.IGNORECASE | re.DOTALL):
        logging.error(f"DeepSeek generated invalid SQL format: {sql_text}. Attempting fallback.")
        deepseek_logger.warning(f"DeepSeek:get_sql_from_deepseek: Generated invalid SQL format. Falling back. Invalid SQL: {sql_text}")
        sql_text = f"SELECT TOP 15 Product_Title, AuthorName1, Category_Name, Product_SalePrice, Product_TitleURl, ISBN13 FROM Table_ProductSearchNewSearch WHERE Product_Title LIKE '%{user_query.split()[0]}%'"
        if len(user_query.split()) > 1:
            sql_text += f" OR AuthorName1 LIKE '%{user_query.split()[0]}%' OR Category_Name LIKE '%{user_query.split()[0]}%'"
        logging.warning(f"DeepSeek:get_sql_from_deepseek: Generated fallback SQL: {sql_text}")
        deepseek_logger.warning(f"DeepSeek:get_sql_from_deepseek: Generated fallback SQL: {sql_text}")

    # Store the generated SQL and loading line in cache if cache is not full
    if len(sql_cache) < MAX_CACHE_SIZE:
        sql_cache[user_query] = (sql_text, loading_line)
        deepseek_logger.info(f"DeepSeek:get_sql_from_deepseek: Stored query in cache for '{user_query}'. Current cache size: {len(sql_cache)}")
    else:
        deepseek_logger.warning("DeepSeek:get_sql_from_deepseek: SQL cache is full. Not caching new query.")
    end_time = time.time()
    deepseek_logger.info(f"DeepSeek:get_sql_from_deepseek: Total SQL generation process time: {end_time - start_time:.4f} seconds.")
    return sql_text, loading_line, token_used

def filter_books_with_deepseek(user_query, books):
    """
    Filters a list of books based on user query using DeepSeek API.

    Args:
        user_query (str): The original user query.
        books (list of dict): List of books retrieved from the database.

    Returns:
        list of int: 0-based indices of the most relevant books.
                     Falls back to returning all original indices if filtering fails.
    """
    # Limit number of books to prevent token overflow and improve performance
    # Only send up to 15-20 books for filtering, as the prompt lists them out.
    books_to_process = books[:20] if len(books) > 20 else books

    # Create a unique key for the cache from the user query and the list of book titles
    cache_key = (user_query, tuple(b.get('Product_Title', '') for b in books_to_process)) 
    
    if cache_key in filter_cache: 
        deepseek_logger.info(f"DeepSeek:filter_books_with_deepseek: Cache hit for user query: '{user_query}'.") 
        return filter_cache[cache_key]
    
    # Prepare book list as plain text with 1-based indexing for DeepSeek
    book_list = "\n".join([
        f"{i+1}. Title: {b.get('Product_Title', 'N/A')}, Author: {b.get('AuthorName1', 'N/A')}, Category: {b.get('Category_Name', 'N/A')}, Price: ₹{b.get('Product_SalePrice', 'N/A')}"
        for i, b in enumerate(books_to_process)
    ])

    prompt = f"""
The user asked: "{user_query}" 
Below is a list of books retrieved from a database. Each book is prefixed with its 1-based number.
Your task is to act as a helpful librarian and choose the book numbers that are the **most relevant** to what the user is looking for. 
**Key Filtering Rules:** 
- Prioritize books that seem most relevant based on the title, author, and category. 
- Consider semantic relevance and user intent. 
- **It is better to return a few closely related books than to return an empty list.** If there are no perfect matches, select the books that are the next best fit. 

Book list (Book Number. Title: ..., Author: ..., Category: ..., Price: ...): 
{book_list} 

**Strict Output Format:** 
Return ONLY the book numbers (e.g., 1, 2, 5) of the most relevant books in a JSON array format like: 
[1, 2, 5] 
If absolutely no books are even remotely relevant, you can return an empty array: [] 
Do not include any other text, markdown, or comments.
"""
    messages = [{"role": "user", "content": prompt.strip()}]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3, # Slightly higher temperature for more diverse filtering, but still low
        "stream": False,
        "max_tokens": 100 # Filtering response should be short
    }

    # Log the query and payload being sent for filtering
    deepseek_logger.info(f"    [AI Filtering] Filtering {len(books_to_process)} books...")

    try:
        start_time = time.time() # Start timer
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=20 # Shorter timeout for filtering
        )
        response.raise_for_status()
        end_time = time.time() # End timer
        duration = end_time - start_time
        # Add a new log message with the duration
        deepseek_logger.info(f"    [AI Filtering] AI call took {duration:.4f}s")

    except requests.exceptions.Timeout:
        logging.error("DeepSeek API call timed out in filter_books_with_deepseek. Falling back to all books.")
        deepseek_logger.error(f"DeepSeek:filter_books_with_deepseek: API call timed out for user query: '{user_query}'. Falling back to all books.")
        return list(range(len(books_to_process))) # Fallback: return all books if filtering times out
    except requests.exceptions.RequestException as e:
        logging.error(f"DeepSeek API request failed in filter_books_with_deepseek: {e}", exc_info=True)
        deepseek_logger.error(f"DeepSeek:filter_books_with_deepseek: API request failed for user query: '{user_query}'. Error: {e}. Falling back to all books.")
        return list(range(len(books_to_process))) # Fallback: return all books if filtering fails

    content = response.json()['choices'][0]['message']['content'].strip()
    # Log the raw response received from DeepSeek for filtering
    deepseek_logger.info(f"DeepSeek:filter_books_with_deepseek: Received raw response from DeepSeek for filtering. Response: {content}")
    
    # Attempt to find the JSON array in the response
    json_match = re.search(r'\[\s*\d*(?:,\s*\d+)*\s*\]', content) # More robust regex for array
    if json_match:
        try:
            selected_indices = json.loads(json_match.group(0))
            # Convert 1-based indices to 0-based, and ensure they are valid
            valid_indices = [i-1 for i in selected_indices if isinstance(i, int) and 0 < i <= len(books_to_process)]
            logging.info(f"DeepSeek:filter_books_with_deepseek: Filtered Indices (0-based): {valid_indices}")
            deepseek_logger.info(f"    [AI Filtering] AI selected {len(valid_indices)} relevant books.")
            #deepseek_logger.info(f"DeepSeek:filter_books_with_deepseek: Filtered Indices (0-based): {valid_indices}")

            if len(filter_cache) < MAX_FILTER_CACHE_SIZE: 
                filter_cache[cache_key] = valid_indices

            return valid_indices
        except json.JSONDecodeError:
            logging.error(f"DeepSeek returned invalid JSON for filtering: '{content}'. Falling back to all books.", exc_info=True)
            deepseek_logger.error(f"DeepSeek:filter_books_with_deepseek: Returned invalid JSON for filtering: '{content}'. Falling back to all books.")
            return list(range(len(books_to_process)))
    
    logging.warning(f"DeepSeek did not return a valid JSON array for filtering: '{content}'. Falling back to all books.")
    deepseek_logger.warning(f"DeepSeek:filter_books_with_deepseek: Did not return a valid JSON array for filtering: '{content}'. Falling back to all books.")
    return list(range(len(books_to_process))) 