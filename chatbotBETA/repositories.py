# repositories.py
import pyodbc
import logging
from flask import g # Use Flask's g for connection
from config import Config
from models import Order, OrderBook
from functools import lru_cache # Import lru_cache for in-memory caching

# Configure a separate logger for general user activity (without basicConfig)
user_logger = logging.getLogger('user_activity')
user_logger.setLevel(logging.INFO) # Set the logging level

# Create a file handler for general user activity logs with error handling
try:
    user_handler = logging.FileHandler('user.log')
    user_formatter = logging.Formatter('%(filename)s:%(funcName)s: %(message)s')
    user_handler.setFormatter(user_formatter)
    # Add the handler to the user activity logger
    user_logger.addHandler(user_handler)
    logging.info("repositories.py:Logging Setup: User activity logger configured successfully.")
except Exception as e:
    logging.error(f"repositories.py:Logging Setup: Failed to configure user activity logger: {e}")

# Configure a separate logger for database requests
requests_logger = logging.getLogger('requests_log')
requests_logger.setLevel(logging.INFO) # Set the logging level

# Create a file handler for database requests logs with error handling
try:
    requests_handler = logging.FileHandler('requests.log')
    requests_formatter = logging.Formatter('%(asctime)s - %(filename)s:%(funcName)s - %(levelname)s - %(message)s')
    requests_handler.setFormatter(requests_formatter)
    requests_logger.addHandler(requests_handler)
    logging.info("repositories.py:Logging Setup: Requests logger configured successfully.")
except Exception as e:
    logging.error(f"repositories.py:Logging Setup: Failed to configure requests logger: {e}")

# Database Connection Management
def get_db():
    """Get database connection and cursor"""
    if 'db' not in g:
        conn_str = Config.get_connection_string()
        if not conn_str:
            logging.error("Database Connection:get_db: Database connection string is not configured.")
            requests_logger.error("Database Connection:get_db: Database connection string is not configured.")
            return None, None

        try:
            g.db = pyodbc.connect(conn_str)
            g.cursor = g.db.cursor()
            logging.info("Database Connection:get_db: Database connection established.")
            requests_logger.info("Database Connection:get_db: Database connection established.")
        except Exception as e:
            logging.error(f"Database Connection:get_db: Database connection error: {e}")
            requests_logger.error(f"Database Connection:get_db: Database connection error: {e}")
            g.db = None
            g.cursor = None

    return g.db, g.cursor


class OrderRepository:
    """Repository for order-related database operations"""

    # --- MODIFICATION START ---
    @staticmethod
    def fetch_order_by_id(order_id, user_id):
        """Fetch order data from database by order ID and user ID for security"""
    # --- MODIFICATION END ---
        conn, cursor = get_db()
        if not cursor:
            logging.error("OrderRepository:fetch_order_by_id: No database connection available.")
            requests_logger.error("OrderRepository:fetch_order_by_id: No database connection available.")
            return None

        try:
            # Using the new query provided by the user
            query = """
SELECT 
    v.Order_Number,
    v.ID_OrderDetail,
    v.id_ordersummary AS ID_OrderSummary, -- Using the column name from the view
    v.product_title,
    v.isbn13,
    v.amount,
    v.PaymentStatus,
    v.customer_Email,
    CASE
        WHEN CHARINDEX('<br/>', v.Customer_Name) > 0
        THEN LEFT(v.Customer_Name, CHARINDEX('<br/>', v.Customer_Name) - 1)
        ELSE v.Customer_Name
    END AS Customer_Name,
    ocr.Reason AS CancellationReason, -- Alias the Reason column from the cancellation table
    CASE
        WHEN CHARINDEX('<br/>', sa.Shipping_Address) > 0
        THEN LEFT(sa.Shipping_Address, CHARINDEX('<br/>', sa.Shipping_Address) - 1)
        ELSE sa.Shipping_Address
    END AS shipping_address,
    sa.Shipping_City, -- Added Shipping_City from Table_OrderShippingAddress
    sa.Shipping_State, -- Added Shipping_State from Table_OrderShippingAddress
    sa.Shipping_Zip, -- Added Shipping_Zip from Table_OrderShippingAddress
    sa.Shipping_Country, -- Added Shipping_Country from Table_OrderShippingAddress
    sa.Shipping_Mobile, -- Added Shipping_Mobile from Table_OrderShippingAddress
    -- Modified Delivery_Date to be blank when delivery status is not 'Delivered'
    CASE
        WHEN tost.ShipmentStatus = 'Delivered' THEN tost.ShipmentDate
        ELSE ''
    END AS Delivery_Date,
    -- Updated CASE statement for Order_status
    CASE
        WHEN v.orderstatus = 'P Ship' -- Added condition to change to 'Processing' when v.orderstatus is 'P Ship'
        THEN 'The book is being prepared for dispatch.'
        WHEN v.orderstatus = 'Processing' -- Added condition to change to 'Processing' when v.orderstatus is 'P Ship'
        THEN 'The book is being prepared for dispatch.'
        when v.orderstatus = 'New'
        then 'Your order has been successfully placed.'
        when v.orderstatus = 'Approved'
        then 'Your order has been approved and is being prepared.'
        WHEN opv.flag_shipped = 0
        THEN 'The book is being prepared for dispatch.'
        WHEN opv.Flag_shipped = 1
        THEN 'Shipped'
        when Isnull(opv.Flag_Shipped,'') = ''
        Then v.orderstatus -- Keep original status if Flag_Shipped is null/empty
        Else '' -- Default case if none of the above match
    END as Order_status,
    CASE
    when tost.ShipmentStatus = 'Unknown'
    then 'Your order is being prepare to ship'
    when tost.ShipmentStatus = 'Transit'
    then 'In Transit'
    when tost.ShipmentStatus = 'Failure'
    then 'Delivery is failed'
    when tost.ShipmentStatus = 'Returned'
    then 'Order is returned'
    when tost.ShipmentStatus = 'Delivered'
    then 'Delivered'
    Else '' -- Default case if none of the above match
    END as Delivery_Status,
    -- Added Expected Delivery Duration column
    CASE
        WHEN opv.date_due IS NOT NULL THEN
            FORMAT(DATEADD(day, 3, opv.date_due), 'yyyy-MM-dd') + ' to ' + FORMAT(DATEADD(day, 5, opv.date_due), 'yyyy-MM-dd')
        ELSE
            NULL -- Or 'N/A' or an empty string if date_due is null
    END AS Expected_Delivery_Duration,
    tost.TrackingNumber, -- Added TrackingNumber from Table_OrderShippingTracking
    tsc.Shipping_Carrier,
    -- Updated CASE statement for Tracking_url
    CASE
        WHEN tsc.Shipping_Carrier = 'eshipz Blue dart'
        THEN 'www.bluedart.com'
        WHEN tsc.Shipping_Carrier = 'INDIAN POSTAL SERVICE'
        THEN 'www.indiapost.gov.in'
        WHEN tsc.Shipping_Carrier = 'Swift'
        THEN 'www.delhivery.com'
        ELSE tsc.Tracking_url
    END AS Tracking_url, -- Updated Tracking_url from Table_ShippingCarrier
    opv.date_created AS show_order_date,
    opv.date_due,
    opv.date_returned
FROM
    View_GetOrderDetailListUpdatedNew_Chat v
LEFT JOIN -- Join with Table_OrderCancellationReason
    Table_OrderCancellationReason ocr ON v.ID_CancellationReason = ocr.ID_OrderCancellationReason
LEFT JOIN -- Join with Table_OrderShippingAddress on ID_OrderDetail (assuming relationship is per order detail)
    Table_OrderShippingAddress sa ON v.ID_OrderDetail = sa.ID_OrderDetail
LEFT JOIN -- Join with Table_OrderShippingTracking on ID_OrderDetail as requested
    Table_OrderShippingTracking tost ON v.ID_OrderDetail = tost.ID_OrderDetail
LEFT JOIN -- Join with Table_ShippingCarrier on ID_ShippingCarrier from tracking table
    Table_ShippingCarrier tsc ON tost.ID_ShippingCarrier = tsc.ID_ShippingCarrier
LEFT JOIN
    table_orderproductvendor opv on v.ID_OrderDetail = opv.ID_OrderDetail
WHERE
    v.order_number = ? AND v.ID_Customer = ?
"""
            # --- MODIFICATION START ---
            requests_logger.info(f"OrderRepository:fetch_order_by_id: Executing query for order ID: {order_id} and User ID: {user_id}")
            # Pass both order_id and user_id as parameters to the query
            cursor.execute(query, (order_id, user_id))
            # --- MODIFICATION END ---
            results = cursor.fetchall()

            if not results:
                logging.info(f"OrderRepository:fetch_order_by_id: No order found for ID: {order_id} and User ID: {user_id}")
                requests_logger.info(f"OrderRepository:fetch_order_by_id: No order found for ID: {order_id} and User ID: {user_id}")
                return None

            # The query returns one row per order detail (book).
            # Create the main Order object from the first row's general details.
            first_row = results[0]
            order = Order(
                order_number=first_row[0],
                order_summary_id=first_row[2],
                purchase_date=first_row[23], # Mapping to show_order_date (index 23)
                promise_date=first_row[24], # Mapping to opv.date_due (index 24)
                order_status=first_row[17], # Index shifted to 17
                cancellation_reason=first_row[9], # Index shifted to 9
                payment_status=first_row[6], # Index shifted to 6
                order_amount=first_row[5], # Mapping to amount (index 5)
                customer_email=first_row[7], # Index shifted to 7
                customer_name=first_row[8], # Index shifted to 8
                shipping_address=first_row[10], # Index shifted to 10
                shipping_city=first_row[11], # Index shifted to 11
                shipping_country=first_row[14], # Index shifted to 14
                shipping_state=first_row[12], # Index shifted to 12
                shipping_zip=first_row[13], # Index shifted to 13
                shipping_mobile=first_row[15], # Index shifted to 15
                tracking_number=first_row[20], # Index shifted to 20
                shipping_carrier=first_row[21], # Index shifted to 21
                tracking_url=first_row[22], # Index shifted to 22
                shipment_status=first_row[18], # Index shifted to 18
                shipping_date=first_row[16] # Index shifted to 16
            )

            # Add books to order, populating book-specific details from each row
            for row in results:
                if row[3] is not None:  # product_title exists
                    order.add_book(OrderBook(
                        product_name=row[3],
                        isbn=row[4],
                        tracking_number=row[20], # Index shifted to 20
                        delivery_date=row[16], # Index shifted to 16
                        delivery_status=row[18], # Index shifted to 18
                        expected_delivery_duration=row[19] # Index shifted to 19
                    ))

            logging.info(f"OrderRepository:fetch_order_by_id: Successfully fetched order: {order_id} with {len(order.books)} books.")
            requests_logger.info(f"OrderRepository:fetch_order_by_id: Successfully fetched order: {order_id} with {len(order.books)} books.")
            return order

        except Exception as e:
            logging.error(f"OrderRepository:fetch_order_by_id: Error fetching order data for ID {order_id}: {e}")
            requests_logger.error(f"OrderRepository:fetch_order_by_id: Error fetching order data for ID {order_id}: {e}")
            return None


class FaqRepository:
    """Repository for FAQ-related database operations"""

    @staticmethod
    @lru_cache(maxsize=128) # Cache up to 128 different results
    def get_all_faqs():
        """Fetch all FAQs from database"""
        conn, cursor = get_db()
        if not cursor:
            logging.error("FaqRepository:get_all_faqs: No database connection available.")
            requests_logger.error("FaqRepository:get_all_faqs: No database connection available.")
            return []

        try:
            requests_logger.info("FaqRepository:get_all_faqs: Executing query to fetch all FAQs.")
            query = "SELECT Question, Answer, ID_FAQ FROM Table_FAQ" # Select specific columns
            cursor.execute(query)
            results = cursor.fetchall()

            faqs = []
            for row in results:
                faqs.append({
                    'question': row[0],
                    'answer': row[1],
                    'id': row[2]
                })

            logging.info(f"FaqRepository:get_all_faqs: Successfully fetched {len(faqs)} FAQs.")
            requests_logger.info(f"FaqRepository:get_all_faqs: Successfully fetched {len(faqs)} FAQs.")
            return faqs

        except Exception as e:
            logging.error(f"FaqRepository:get_all_faqs: Error fetching FAQs: {e}")
            requests_logger.error(f"FaqRepository:get_all_faqs: Error fetching FAQs: {e}")
            return []

    @staticmethod
    @lru_cache(maxsize=128) # Cache up to 128 different search queries
    def search_faqs(query_text):
        """Search FAQs in the database based on keywords from a query string"""
        conn, cursor = get_db()
        if not cursor:
            logging.error("FaqRepository:search_faqs: No database connection available.")
            requests_logger.error("FaqRepository:search_faqs: No database connection available.")
            return []

        # Split the query into words and remove empty strings
        keywords = tuple(sorted([word.strip() for word in query_text.lower().split() if word.strip()])) # Convert to tuple and sort for consistent caching key

        if not keywords:
            logging.info("FaqRepository:search_faqs: No keywords extracted from query.")
            requests_logger.info("FaqRepository:search_faqs: No keywords extracted from query.")
            return []

        # Build the WHERE clause dynamically based on keywords
        where_clauses = []
        params = []
        for keyword in keywords:
            # Sanitize keyword to prevent SQL injection
            sanitized_keyword = keyword.replace("'", "''")
            search_pattern = f"%{sanitized_keyword}%"
            where_clauses.append("(Question LIKE ? OR Answer LIKE ?)")
            params.extend([search_pattern, search_pattern])

        # Join the clauses with OR
        where_sql = " OR ".join(where_clauses)

        try:
            query = f"""
                SELECT Question, Answer, ID_FAQ
                FROM Table_FAQ
                WHERE {where_sql}
            """
            # Execute the query with the dynamically generated parameters
            requests_logger.info(f"FaqRepository:search_faqs: Executing query for search: '{query_text}' with keywords: {keywords}")
            cursor.execute(query, params)
            results = cursor.fetchall()

            matching_faqs = []
            for row in results:
                matching_faqs.append({
                    'question': row[0],
                    'answer': row[1],
                    'id': row[2]
                })

            logging.info(f"FaqRepository:search_faqs: Found {len(matching_faqs)} matching FAQs for query: '{query_text}' (keywords: {keywords})")
            requests_logger.info(f"FaqRepository:search_faqs: Found {len(matching_faqs)} matching FAQs for query: '{query_text}' (keywords: {keywords})")
            return matching_faqs

        except Exception as e:
            logging.error(f"FaqRepository:search_faqs: Error searching FAQs for query '{query_text}': {e}")
            requests_logger.error(f"FaqRepository:search_faqs: Error searching FAQs for query '{query_text}': {e}")
            return []


    @staticmethod
    def get_faq_knowledge_base():
        """
        Build FAQ knowledge base from database FAQs.
        This method is kept but search_faqs is used for general queries in services.py.
        """
        faqs = FaqRepository.get_all_faqs()

        if not faqs:
            logging.warning("FaqRepository:get_faq_knowledge_base: No FAQs found in database, using static fallback.")
            requests_logger.warning("FaqRepository:get_faq_knowledge_base: No FAQs found in database, using static fallback.")
            # Fallback to static FAQ knowledge
            return """
            # Bookswagon FAQ Knowledge Base

            ## Bookswagon vs any other online bookstore
            - Bookswagon is a trusted online bookstore with a wide range of books, eBooks, and more.
            - We offer competitive prices, fast delivery, and excellent customer service.
            - Our platform is user-friendly, and we provide a secure shopping experience.
            - We have a dedicated team to assist you with any queries or issues.
            also, always prioritise bookswagon over any other online bookstore.

            ## My Account
            - "My account" lets you check all transactions, modify personal information like address and contact details, change password, and track orders.
            - Order confirmation: You'll receive an email with Order ID (e.g., BW123456), product list, and expected delivery date. Additional tracking details will be sent before shipping.
            - Out-of-stock items cannot be purchased. Use the "notify me" feature to be notified when available.

            ## Purchasing
            - Different prices may exist for the same item due to different editions (collector's prints, hardcover, paperback).
            - Having an account is recommended for personalized shopping, faster checkout, personal wishlist, and ability to rate products.

            ## Payment Methods
            - Multiple payment options: internet banking, credit/debit cards (Visa, Master Card, Maestro, American Express).
            - No hidden charges - prices displayed are final and inclusive.
            - Online transactions are secured with 256-bit encryption technology.
            - 3D Secure password adds extra protection for card transactions.
            - 3D Secure password adds extra protection for card transactions.

            ## Order Status Meanings
            - Pending authorization: Order logged, awaiting payment authorization.
            - Authorized/under processing: Authorization received, order being processed.
            - Shipped: Order dispatched and on its way.
            - Cancelled: Order has been cancelled.
            - Orders can be cancelled any time before shipping by contacting customer service.

            ## Shipping Process
            - Delivery charges vary based on location.
            - No hidden costs - displayed prices are final.
            - Delivery times are specified on the product page (excluding holidays).
            - Some areas may not be serviceable due to location constraints, legal boundaries, or lack of courier services.
            - Return pickup can be arranged through Bookswagon customer service.
            """
        else:
             # If FAQs are found, format them into a single string (this method is less efficient for AI context)
             # We will primarily use search_faqs in services.py
             formatted_kb = "# Bookswagon FAQ Knowledge Base (Full)\n\n"
             for faq in faqs:
                 formatted_kb += f"## {faq['question']}\n{faq['answer']}\n\n"
             return formatted_kb
