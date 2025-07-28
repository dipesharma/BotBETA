# services.py
import logging
import re
import json
import requests
from datetime import datetime, timedelta # Import for date calculations
from config import Config # Required for accessing API keys and URLs
from repositories import FaqRepository # Required for getting FAQ data
# No direct import of db_utils or sql_utils here, services use repositories which use db_utils

# --- CACHE for General Responses ---
general_response_cache = {}
MAX_GENERAL_CACHE_SIZE = 1000

# Services
class AIService:
    """Service for AI-related operations using DeepSeek API"""

    # Constants
    EXIT_COMMANDS = ["exit", "quit", "bye", "goodbye", "thanks", "thank you", "धन्यवाद", "अलविदा", "बाय", "tata", "ta ta"]
    GREETINGS = ["hello", "hi", "hey", "namaste", "hola", "good morning", "good afternoon", "good evening", "hii"]
    CHAT_HISTORY_LIMIT = 10 # Max number of past messages to include in API requests

    @staticmethod
    def query_deepseek(messages, temperature=0.1):
        """Send messages to DeepSeek API and return the response"""
        api_key = Config.DEEPSEEK_API_KEY
        model = Config.DEEPSEEK_MODEL

        if not api_key or api_key == "sk-YOUR_DEFAULT_API_KEY_IF_NEEDED": # Check for default or missing API key
            logging.error("AIService:query_deepseek: DeepSeek API key not set.")
            return "My apologies! My brain is on a brief break. Please try again in a bit."

        try:
            url = Config.DEEPSEEK_API_URL
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1024 # Define a reasonable max token limit
            }
            logging.info(f"AIService:query_deepseek: Sending request to DeepSeek with payload (first message): {payload['messages'][0]['content'][:150]}...")
            response = requests.post(url, headers=headers, json=payload)
            logging.info(f"AIService:query_deepseek: HTTP status code: {response.status_code}")
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

            try:
                response_data = response.json()
            except json.JSONDecodeError as e: # Specific exception for JSON parsing errors
                logging.error(f"AIService:query_deepseek: Failed to parse JSON: {e}")
                logging.error(f"Raw response content: {response.text}")
                return "Oops! I heard gibberish. My apologies, please try again!"

            # Defensive structure validation for the API response
            if (
                isinstance(response_data, dict)
                and "choices" in response_data
                and isinstance(response_data["choices"], list)
                and len(response_data["choices"]) > 0
                and isinstance(response_data["choices"][0], dict) # Ensure the first choice is a dict
                and "message" in response_data["choices"][0]
                and isinstance(response_data["choices"][0]["message"], dict) # Ensure message is a dict
                and "content" in response_data["choices"][0]["message"]
            ):
                final_content = response_data["choices"][0]["message"]["content"]
                logging.info(f"AIService:query_deepseek: Final AI message (first 150 chars): {final_content[:150]}...")
                return final_content.strip()
            else:
                logging.error(f"AIService:query_deepseek: Unexpected response structure from DeepSeek API.")
                logging.error(f"Response data: {json.dumps(response_data, indent=2)}")
                return "My apologies! I received a message that didn't quite make sense to me. Could you try again?"

        except requests.exceptions.HTTPError as e:
            logging.error(f"AIService:query_deepseek: HTTPError {e.response.status_code}: {e.response.text}")
            return f"Oops! It seems I'm having a little trouble dialing up my knowledge base right now. Please try again in a moment!"
        except requests.exceptions.RequestException as e: # Catch other requests-related errors
            logging.error(f"AIService:query_deepseek: RequestException: {str(e)}", exc_info=True)
            return "My apologies! I'm having a spot of trouble reaching the larger library of information. Please give it another try in a bit!"
        except Exception as e:
            logging.error(f"AIService:query_deepseek: Unexpected error: {str(e)}", exc_info=True)
            return "Whoops! I've encountered a mysterious plot twist on my end. My apologies, please try again shortly!"

    @staticmethod
    def detect_user_intent(user_query, chat_history_api_format):
        """
        Uses DeepSeek to classify the user's intent.

        Args:
            user_query (str): The user's current query.
            chat_history_api_format (list): Formatted list of previous messages for the API.

        Returns:
            str: The detected intent ('recommend_books', 'order', 'general_faq', 'unknown').
        """
        intent_prompt = """
        You are an intent detection system for a Bookswagon customer service chatbot.
        Analyze the user's query and the recent chat history to determine the user's primary intent.

        Classify the intent into one of the following categories:
        - 'recommend_books': The user is asking for book recommendations, suggestions, or searching for books by topic, genre, author, etc. (e.g., "recommend a sci-fi book", "books about history", "find books by Jane Austen", "tell me the cost or mrp or price of ikigai", "is ikigai available?", "share the link for harrison's principles").
        - 'order': The user is asking about a specific order, its status, tracking, delivery, cancellation, payment, or providing an order number. (e.g., "where is my order BW123456", "check status of order", "cancel this item", "payment issue for order").
        - 'general_faq': The user is asking a general question about Bookswagon services, policies, account, payment methods, shipping process, or anything not covered by book recommendations or specific orders. (e.g., "how to return a book", "what payment methods do you accept", "create an account", "about Bookswagon").
        - 'unknown': The user's intent is unclear, irrelevant to Bookswagon, or falls outside the defined categories.

        Consider the chat history to understand the context, but prioritize the latest user query.

        Return ONLY the intent category string. Do not include any other text, explanation, or markdown.
        Example Output:
        recommend_books

        Example Output:
        order

        Example Output:
        general_faq

        Example Output:
        unknown

        If the user is saying goodbye or thank you (e.g., "bye", "thank you", "धन्यवाद"), classify this as 'general_faq' as it's a standard interaction closing.

        """

        messages_for_api = [
            {"role": "system", "content": intent_prompt},
            *chat_history_api_format[-AIService.CHAT_HISTORY_LIMIT:], # Include recent chat history for context
            {"role": "user", "content": user_query}
        ]

        try:
            # Use a very low temperature for deterministic intent classification
            ai_response_content = AIService.query_deepseek(messages_for_api, temperature=0.0).strip().lower()

            # Validate the response against expected intents
            valid_intents = ['recommend_books', 'order', 'general_faq', 'unknown']
            if ai_response_content in valid_intents:
                logging.info(f"AIService:detect_user_intent: Detected intent: {ai_response_content}")
                return ai_response_content
            else:
                logging.warning(f"AIService:detect_user_intent: DeepSeek returned unexpected intent '{ai_response_content}'. Falling back to 'unknown'.")
                # Attempt to check for specific keywords as a fallback for unexpected AI output
                if "book" in user_query.lower() or "recommend" in user_query.lower() or "suggest" in user_query.lower():
                    return 'recommend_books'
                elif "order" in user_query.lower() or "bw" in user_query.lower():
                    return 'order'
                elif any(cmd in user_query.lower() for cmd in AIService.EXIT_COMMANDS + AIService.GREETINGS):
                     return 'general_faq' # Treat greetings/exits as general chat
                else:
                    return 'general_faq' # Default to general FAQ if AI fails and no keywords match

        except Exception as e:
            logging.error(f"AIService:detect_user_intent: Error during AI intent detection: {e}", exc_info=True)
            # Fallback to a default intent if AI call fails
            logging.warning("AIService:detect_user_intent: AI intent detection failed. Falling back to basic keyword check.")
            # Basic fallback based on keywords if AI call fails
            if "book" in user_query.lower() or "recommend" in user_query.lower() or "suggest" in user_query.lower():
                return 'recommend_books'
            elif "order" in user_query.lower() or "bw" in user_query.lower():
                return 'order'
            elif any(cmd in user_query.lower() for cmd in AIService.EXIT_COMMANDS + AIService.GREETINGS):
                 return 'general_faq' # Treat greetings/exits as general chat
            else:
                 return 'general_faq' # Default to general FAQ if AI fails and no keywords match


    @staticmethod
    def extract_order_id(text):
        """Extract Bookswagon order ID (e.g., BW123456) from text using regex."""
        # Updated regex to be more flexible with digits after BW
        pattern_bw = r'\b(BW\d+)\b' # BW followed by one or more digits
        match_bw = re.search(pattern_bw, text, re.IGNORECASE)
        if match_bw:
            return match_bw.group(0).upper()
        return None

    @staticmethod
    def detect_language(text):
        """
        Detect if text contains Hindi or Hinglish keywords or Devanagari script.
        """
        hindi_keywords = [
            "kya", "hai", "mera", "kahan", "kyu", "kyun", "kaise", "kab", "aap", "hum",
            "नमस्ते", "धन्यवाद", "कैसा", "हैं", "शुभ", "प्रभात", "दोपहर", "संध्या",
            "ऑर्डर", "किताब", "सहायता", "जानकारी", "पुस्तक", "नमस्ते", "नमस्कार"
        ]
        # Check for keywords or Devanagari script
        if any(keyword in text.lower() for keyword in hindi_keywords) or re.search(r'[\u0900-\u097F]+', text):
            return True
        return False

    @staticmethod
    def get_response_in_language(response, is_hindi):
        """
        Translate response to Hindi/Hinglish if is_hindi is True using DeepSeek.
        """
        if is_hindi:
            translation_prompt = f"""
            Translate this customer service response to natural-sounding Hindi or Hinglish, as appropriate for a friendly assistant named Vidya.
            Maintain the original meaning, politeness, and helpful tone.
            If the original response contains specific details like order numbers, dates, or product names, ensure they are preserved accurately in the translation.

            Original English Text: "{response}"

            Provide ONLY the translated text. Do not add any extra phrases like "Here's the translation:".
            """
            try:
                # Using a slightly higher temperature for more natural-sounding translation
                translated_response = AIService.query_deepseek([{"role": "user", "content": translation_prompt}], temperature=0.6).strip()
                # Remove any markdown like '#' or '*' that might be added by the AI
                translated_response = re.sub(r'[#*]', '', translated_response).strip()
                logging.info(f"AIService:get_response_in_language: Translated response: {translated_response[:150]}...")
                return translated_response
            except Exception as e:
                logging.error(f"AIService:get_response_in_language: Error translating to Hindi/Hinglish: {e}")
                # Fallback to English response if translation fails
                logging.warning("AIService:get_response_in_language: Translation failed, falling back to English.")
                pass # Continue to return original response

        # If not Hindi or if translation failed, return the original response (cleaned)
        response = re.sub(r'[#*]', '', response).strip()
        return response


    @staticmethod
    def generate_order_summary(order, user_query, is_hindi, chat_history_api_format):
        """
        Generate AI response about a specific order using order details, relevant FAQs, and chat history.
        Includes individual book delivery details and refined return policy info.
        """
        if not order:
            logging.warning("AIService:generate_order_summary: Called with no order object.")
            return "I'm sorry, but I don't have any active order details to discuss. Could you please provide an order number if you have one?"

        order_data = order.to_dict()
        order_details = order_data.get('order_details', {})
        books = order_data.get('books', [])

        payment_status_meanings = {
            "Cre Pending": "Refund is in process or awaiting confirmation to be credited to your account.",
            "Credit": "Refund has been successfully credited to your account.",
            "Pending": "Payment is currently being processed. Please allow some time for it to complete.",
            "Processed": "Payment has been successfully completed and finalized.",
            "Void": "The transaction was cancelled before completion, so no funds were transferred."
        }
        payment_status = order_details.get('payment_status', 'Unknown')
        payment_status_meaning = payment_status_meanings.get(payment_status, "The current payment status is not clearly defined. For more details, please check your account or contact support.")

        # Dynamically fetch relevant FAQs based on the user's query
        relevant_faqs = FaqRepository.search_faqs(user_query)
        faq_knowledge_for_ai = ""
        if relevant_faqs:
            faq_knowledge_for_ai = "# Relevant Bookswagon FAQ Information:\n"
            for faq in relevant_faqs:
                faq_knowledge_for_ai += f"- Question: {faq.get('question', 'N/A')}\n  Answer: {faq.get('answer', 'N/A')}\n\n"
        else:
            faq_knowledge_for_ai = "No specific FAQ entries were found directly matching your query. I'll use general Bookswagon policies and the order details to help you."

        # Construct detailed order information string
        detailed_order_info = (
            f"Order Number: {order_details.get('order_number', 'N/A')}\n"
            f"Customer Name: {order_details.get('customer_name', 'N/A')}\n"
            f"Purchase Date: {order_details.get('purchase_date', 'N/A')}\n"
            f"Current Overall Order Status: {order_details.get('order_status', 'N/A')}\n"
            f"Payment Status: {payment_status} - {payment_status_meaning}\n"
            f"Total Amount: {order_details.get('order_amount', 'N/A')}\n"
        )

        # Shipping Address and Contact
        address_parts = []
        for field in ['shipping_address', 'shipping_city', 'shipping_state', 'shipping_zip', 'shipping_country']:
            value = str(order_details.get(field, '')).strip()
            if value and value.lower() != 'n/a':
                address_parts.append(value.title())
        if address_parts:
            detailed_order_info += f"Shipping Address: {', '.join(address_parts)}\n"

        mobile = str(order_details.get('shipping_mobile', '')).strip()
        if mobile and mobile.lower() != 'n/a':
            detailed_order_info += f"Contact Mobile: {mobile}\n"

        # Individual Book Details with Delivery Info
        detailed_order_info += "Products in Order:\n"
        if books:
            for i, book in enumerate(books, 1):
                book_info = f"  {i}. {book.get('product_name', 'N/A')}\n"

                # Conditional display of delivery information for each book
                book_delivery_date_str = book.get('delivery_date')
                book_expected_delivery_duration = book.get('expected_delivery_duration')
                book_delivery_status = book.get('delivery_status')
                book_tracking_number = book.get('tracking_number') # Get book-specific tracking
                order_tracking_url = order_details.get('tracking_url') # Get order-level tracking URL

                if book_tracking_number and book_tracking_number != 'N/A':
                    book_info += f"     Tracking Number: {book_tracking_number}\n"
                    if order_tracking_url and order_tracking_url != 'N/A':
                         book_info += f"     Tracking URL: {order_tracking_url}\n"
                    else:
                         book_info += f"     For tracking updates, please visit the Bookswagon website and use your tracking number.\n"


                if book_delivery_date_str and book_delivery_date_str != 'N/A':
                     book_info += f"     Delivery Status: {book_delivery_status or 'N/A'}\n"
                     book_info += f"     Delivery Date: {book_delivery_date_str}\n"

                     # Check for return eligibility based on 15-day window
                     try:
                         delivery_date = datetime.strptime(book_delivery_date_str, "%Y-%m-%d")
                         # Current date for comparison
                         current_date = datetime.now()
                         return_window_end = delivery_date + timedelta(days=7)

                         if current_date > return_window_end:
                             book_info += "     Return Status: Not eligible for standard return (7-day window passed).\n"
                         else:
                             days_left = (return_window_end - current_date).days
                             book_info += f"     Return Status: Eligible for return. You have {days_left} days left to return.\n"

                     except ValueError:
                         logging.warning(f"AIService:generate_order_summary: Could not parse delivery date {book_delivery_date_str} for return calculation.")
                         book_info += "     Return status could not be determined due to invalid delivery date.\n"

                elif book_expected_delivery_duration and book_expected_delivery_duration != 'N/A':
                     book_info += f"     Expected Delivery Duration: {book_expected_delivery_duration}\n"
                # No specific fallback for individual books if both are missing, AI can infer from overall status

                detailed_order_info += book_info

        else:
            detailed_order_info += "  No books listed for this order.\n"

        # General return policy statement, without specific mention of damaged goods unless queried
        detailed_order_info += "\nReturn Policy Information:\n"
        detailed_order_info += "  Bookswagon allows returns within 7 days of delivery for most items. For detailed instructions on how to initiate a return, please visit our website or contact customer support.\n"

        # Add condition to include damaged book policy only if relevant keywords are in user_query
        if re.search(r'\b(damaged|defective|broken|faulty)\b', user_query.lower()):
            detailed_order_info += "  If your book arrived damaged or defective, you may be eligible for a refund beyond the standard return window. Please report such issues within 48 hours of delivery by contacting customer care.\n"


        # System prompt for the AI
        system_prompt = f"""
        You are Vidya, Bookswagon's friendly and helpful customer service AI assistant.
        Your primary goal is to assist users with their Bookswagon orders, book searched and related queries and answer general inquiries based ONLY on the information provided below and the ongoing chat history.

        Current User Language Preference: {"Hindi/Hinglish" if is_hindi else "English"}. Respond naturally in this language.

        === DETAILED ORDER INFORMATION (Order: {order_details.get('order_number', 'N/A')}) ===
        {detailed_order_info}
        === END OF DETAILED ORDER INFORMATION ===

        === RELEVANT FAQ INFORMATION (Based on current query) ===
        {faq_knowledge_for_ai}
        === END OF RELEVANT FAQ INFORMATION ===

        === CHAT HISTORY (Recent messages) ===
        [The chat history will be injected here by the system]
        === END OF CHAT HISTORY ===

        Your Task:
        1.  Carefully analyze the USER'S CURRENT QUERY in the context of the CHAT HISTORY.
        2.  Use the DETAILED ORDER INFORMATION to answer questions specifically about order {order_details.get('order_number', 'N/A')}. Provide specific details for individual books if the query relates to them (e.g., tracking, delivery, return eligibility).
        3.  When providing tracking information, if a direct URL is available, share it. If not, explicitly tell the user to track their order on the Bookswagon website using the provided tracking number. DO NOT make assumptions about tracking URLs if they are not explicitly present.
        4.  For return inquiries, state the standard 7-day return policy from the delivery date. If the 7-day window has passed for a specific book, clearly state that it's no longer eligible for a standard return. ONLY provide information about returning damaged or defective books if the user's query specifically mentions keywords like "damaged", "defective", "broken", or "faulty". And return policy is strictly of 7 days including that of damaged/defective books, do not mention any exceptions and direct the request to customer care.
        5.  Use the RELEVANT FAQ INFORMATION for general questions or if the order details don't cover the query.
        6.  If a book's expected delivery date has passed and its status isn't 'Delivered' or 'Cancelled', express concern, apologize for the delay regarding that specific item, and advise the user to contact Bookswagon customer care for an urgent update about that book or the order, providing the order number.
        7.  Maintain a warm, empathetic, and professional tone. Be concise but thorough.
        8.  DO NOT invent or assume any information not present in the provided details or FAQs. If you don't know, say so politely.
        9.  DO NOT offer to perform actions yourself (e.g., "I will cancel this book"). Instead, guide the user on how they can do it.
        10. Always conclude by asking if there's anything else you can help with.
        11. If the user's query is completely unrelated to Bookswagon orders or services after reviewing all provided context, politely state that you are here to help with Bookswagon-related queries.
        12. Always show the positive side of bookswagon and its services, even if the user is frustrated or angry. Use phrases like "I understand your concern" or "I appreciate your patience" to acknowledge their feelings.
        13. Do not show the potential concerns or anything negative about bookswagon.
        14. Do NOT use any emojis in your response.
        15. Always prioritize customer care email over customer care phone number. If user asks for customer care phone number then only give it.
        """

        # Prepare messages for the API, including chat history
        messages_for_api = [
            {"role": "system", "content": system_prompt},
            *chat_history_api_format[-AIService.CHAT_HISTORY_LIMIT:], # Include recent chat history
            {"role": "user", "content": user_query}
        ]

        ai_response_content = AIService.query_deepseek(messages_for_api, temperature=0.7)

        # The translation should be applied to the final AI response content
        return AIService.get_response_in_language(ai_response_content, is_hindi)

    @staticmethod
    def generate_general_response(user_query, is_hindi, chat_history_api_format):
        """
        Generate AI response for general inquiries using relevant FAQs and chat history.
        """
        # Dynamically fetch relevant FAQs based on the user's query
        relevant_faqs = FaqRepository.search_faqs(user_query)
        faq_knowledge_for_ai = ""
        if relevant_faqs:
            faq_knowledge_for_ai = "# Relevant Bookswagon FAQ Information:\n"
            for faq in relevant_faqs:
                faq_knowledge_for_ai += f"- Question: {faq.get('question', 'N/A')}\n  Answer: {faq.get('answer', 'N/A')}\n\n"
        else:
            faq_knowledge_for_ai = "No specific FAQ entries were found directly matching your query. I'll answer based on general Bookswagon knowledge."


        system_prompt = f"""
        You are Vidya, a versatile and knowledgeable bookstore assistant.
        Your primary goal is to answer general inquiries about Bookswagon services, policies, and information based ONLY on the provided FAQ information and the ongoing chat history. You should also guide users if they are asking about an order by asking for their order number.

        Current User Language Preference: {"Hindi/Hinglish" if is_hindi else "English"}. Respond naturally in this language.

        === RELEVANT FAQ INFORMATION (Based on current query) ===
        {faq_knowledge_for_ai}
        === END OF RELEVANT FAQ INFORMATION ===

        === CHAT HISTORY (Recent messages) ===
        [The chat history will be injected here by the system]
        === END OF CHAT HISTORY ===

        Your Task:
        1.  Carefully analyze the USER'S CURRENT QUERY in the context of the CHAT HISTORY.
        2.  Use the RELEVANT FAQ INFORMATION to answer the user's question directly and accurately.
        3.  If the user's query is about an order (e.g., "my order", "status", "delivery"), but they haven't provided an order number, politely ask for the order number (e.g., "Could you please provide your order number so I can assist you?"). Mention that order numbers typically start with 'BW'.
        4.  Maintain a warm, empathetic, and professional tone. Be concise but thorough.
        5.  DO NOT invent or assume any information not present in the provided FAQs. If you don't know, say so politely and suggest contacting customer care.
        6.  DO NOT offer book recommendations; direct users asking for book suggestions to the book recommendation feature if possible, or simply state that you are here for customer service queries.
        7.  Always conclude by asking if there's anything else you can help with.
        8.  If the user's query is completely unrelated to Bookswagon services after reviewing all provided context, politely state that you are here to help with Bookswagon-related customer service queries.
        9.  You cannot escalate things yourself, but you can guide the user on how to contact customer care for urgent issues.
        10. Give tracking details of individual items if available no matter the complete order is shipped or not, fetching from the database column tracking_url, else tell them to visit the Bookswagon website with their tracking number, do not give bookswagon link.
        11. Do not tell the return policy if the user is not asking for it, but if they are asking for it, tell them the standard 7-day return policy from the delivery date. If the 7-day window has passed for a specific book, clearly state that it's no longer eligible for a standard return.
        12. Do NOT use any emojis in your response.
        13. Do not write anything like, " According to the FAQ, I can say that..." or "Based on the FAQ, I can tell you that...".
        14. Do not mention about damaged and return books until and unless customer asks for it. And Return policy is strictly of 7 days, do not mention any exceptions and direct the request to customer care.
        15. Always prioritize customer care email over customer care phone number. If user asks for customer care phone number then only give it
        16. If the user asks a personal or conversational question (e.g., "how are you?", "what are you doing?"), you MUST respond with a short, creative, in-character "persona" response as Vidya, the bookstore assistant. Your response must be warm and clever, and it must always pivot back to the topic of books or helping the user. Be diverse and do not use the same response every time.
        """
        # Prepare messages for the API, including chat history
        messages_for_api = [
            {"role": "system", "content": system_prompt},
            *chat_history_api_format[-AIService.CHAT_HISTORY_LIMIT:], # Include recent chat history
            {"role": "user", "content": user_query}
        ]

        ai_response_content = AIService.query_deepseek(messages_for_api, temperature=0.7)

        final_response = AIService.get_response_in_language(ai_response_content, is_hindi)

        return final_response
 


class FormatterService:
    """Service for formatting order data and responses for display"""

    @staticmethod
    def format_order_response(order):
        """
        Format order details into a clean, human-readable string for display without markdown symbols.
        Includes individual book delivery details with 1-based indexing.

        Args:
            order (Order): The Order object.

        Returns:
            str: A formatted string of order details.
        """
        if not order:
            return "Order details not found or could not be processed."

        order_data = order.to_dict()
        order_details = order_data.get('order_details', {})
        books = order_data.get('books', [])
        book_details_list = []
        # Payment status descriptions without symbols
        payment_status_meanings = {
            "Cre Pending": "Refund is in process or awaiting confirmation to be credited.",
            "Credit": "Refund successfully credited.",
            "Pending": "Payment is still being processed or awaiting confirmation.",
            "Processed": "Payment has been successfully completed.",
            "Void": "Transaction was cancelled before completion; no funds were moved."
        }
        payment_status = order_details.get('payment_status', 'N/A')
        payment_status_meaning = payment_status_meanings.get(payment_status, "Status not clearly defined. Please check your account for details.")

        # Building the formatted response string without markdown
        response_parts = [
            f"Order Details for {order_details.get('order_number', 'N/A')}",
            f"Customer: {str(order_details.get('customer_name', 'N/A')).strip().title()}",
            f"Purchase Date: {order_details.get('purchase_date', 'N/A')}",
            f"Overall Order Status: {order_details.get('order_status', 'N/A')}", # Clarified as Overall
            f"Payment Status: {payment_status} - {payment_status_meaning}",
            f"Total Amount: {order_details.get('order_amount', 'N/A')}"
        ]

        # Shipping address on a single line
        address_parts = []
        for field in ['shipping_address', 'shipping_city', 'shipping_state', 'shipping_zip', 'shipping_country']:
            value = str(order_details.get(field, '')).strip()
            if value and value.lower() != 'n/a':
                address_parts.append(value.title())

        if address_parts:
            response_parts.append(f"Shipping Address: {', '.join(address_parts)}")

        # Contact info if available
        mobile = str(order_details.get('shipping_mobile', '')).strip()
        if mobile and mobile.lower() != 'n/a':
            response_parts.append(f"Contact: {mobile}")


        # Individual Book Details with Delivery Info
        response_parts.append("Books Ordered:")
        if books:
            for i, book in enumerate(books, 1):
                book_info_lines = [
                    # --- Display 1-based index for the book ---
                    f"{i}. {book.get('product_name', 'N/A')}"
                ]

                book_tracking_number = book.get('tracking_number') # Get book-specific tracking
                order_tracking_url = order_details.get('tracking_url') # Get order-level tracking URL

                if book_tracking_number and book_tracking_number != 'N/A':
                     book_info_lines.append(f"   Tracking Number: {book_tracking_number}")
                     if order_tracking_url and order_tracking_url != 'N/A':
                          book_info_lines.append(f"   Tracking URL: {order_tracking_url}")
                     else:
                          book_info_lines.append(f"   Please visit the Bookswagon website to track this book using the tracking number.")


                # Conditional display of delivery information for the specific book
                book_delivery_date_str = book.get('delivery_date')
                book_expected_delivery_duration = book.get('expected_delivery_duration')
                book_delivery_status = book.get('delivery_status')


                if book_delivery_date_str and book_delivery_date_str != 'N/A':
                     book_info_lines.append(f"   Delivery Status: {book_delivery_status or 'N/A'}")
                     book_info_lines.append(f"   Delivery Date: {book_delivery_date_str}")

                     # Check for return eligibility based on 7-day window
                     try:
                         delivery_date = datetime.strptime(book_delivery_date_str, "%Y-%m-%d")
                         current_date = datetime.now()
                         return_window_end = delivery_date + timedelta(days=7)

                         if current_date > return_window_end:
                             book_info_lines.append("   Return Status: Not eligible for standard return (7-day window passed).")
                         else:
                             days_left = (return_window_end - current_date).days
                             book_info_lines.append(f"   Return Status: Eligible for return. You have {days_left} days left to return.")

                     except ValueError:
                         book_info_lines.append("   Return status could not be determined due to invalid delivery date.")


                elif book_expected_delivery_duration and book_expected_delivery_duration != 'N/A':
                     book_info_lines.append(f"   Expected Delivery Duration: {book_expected_delivery_duration}")
                # No specific fallback for individual books if both are missing


                book_details_list.append("\n".join(book_info_lines))

        if book_details_list:
             return "\n".join(response_parts) + "\n\n" + "\n\n".join(book_details_list)
        else:
             return "\n".join(response_parts) + "\n\nNo books listed for this order."


    @staticmethod
    def parse_book_indices(user_input, total_books):
        """
        Extract book indices (0-based) from user input (e.g., '1,2,3' or '1 2 3').
        Filters for valid indices within the total number of books.
        """
        if not isinstance(user_input, str): # Basic type check
            return []

        # Replace commas and multiple spaces with a single space for easier splitting
        cleaned_input = re.sub(r',', ' ', user_input)
        cleaned_input = re.sub(r'\s+', ' ', cleaned_input).strip()

        parts = cleaned_input.split(' ')
        indices = []
        for part in parts:
            if not part.isdigit(): # Skip non-numeric parts
                continue
            try:
                # Convert to 0-based index
                idx = int(part) - 1
                if 0 <= idx < total_books: # Check if index is valid
                    if idx not in indices: # Avoid duplicate indices
                        indices.append(idx)
            except ValueError:
                # Handles cases where part might be empty string after split or other non-int
                continue

        return sorted(indices) # Return sorted unique indices

    @staticmethod
    def format_specific_books_response(order, indices):
        """
        Format details for specific books in an order based on provided indices.
        Includes individual book delivery details with 1-based indexing.
        """
        if not order or not hasattr(order, 'books') or not order.books or not indices:
            return "Could not find details for the requested books, or the order/book list is empty."

        book_details_list = []
        order_number = order.order_number if hasattr(order, 'order_number') else 'N/A'
        order_details = order.to_dict().get('order_details', {})
        order_tracking_url = order_details.get('tracking_url', 'N/A') # Get order-level tracking URL here

        # Assuming books in order.books are already in the correct order from the query
        for i in indices:
             # Check index validity based on 0-based list but display 1-based
            if 0 <= i < len(order.books):
                book = order.books[i] # Access book by 0-based index
                book_info_lines = [
                    # --- Display 1-based index for the book ---
                    f"Details for Book {i + 1} in Order {order_number}:",
                    f"- Product: {book.product_name or 'Unknown Product'}"
                ]

                book_tracking_number = book.get('tracking_number') # Get book-specific tracking
                if book_tracking_number and book_tracking_number != 'N/A':
                     book_info_lines.append(f"- Tracking Number: {book_tracking_number}")
                     if order_tracking_url and order_tracking_url != 'N/A':
                          book_info_lines.append(f"- Tracking URL: {order_tracking_url}")
                     else:
                          book_info_lines.append(f"- Please visit the Bookswagon website to track this book using the tracking number.")


                # Conditional display of delivery information for the specific book
                book_delivery_date_str = book.get('delivery_date')
                book_expected_delivery_duration = book.get('expected_delivery_duration')
                book_delivery_status = book.get('delivery_status')


                if book_delivery_date_str and book_delivery_date_str != 'N/A':
                     book_info_lines.append(f"- Delivery Status: {book_delivery_status or 'N/A'}")
                     book_info_lines.append(f"- Delivery Date: {book_delivery_date_str}")

                     # Check for return eligibility based on 7-day window
                     try:
                         delivery_date = datetime.strptime(book_delivery_date_str, "%Y-%m-%d")
                         current_date = datetime.now()
                         return_window_end = delivery_date + timedelta(days=7)

                         if current_date > return_window_end:
                             book_info_lines.append("- Return Status: Not eligible for standard return (7day window passed).")
                         else:
                             days_left = (return_window_end - current_date).days
                             book_info_lines.append(f"- Return Status: Eligible for return. You have {days_left} days left to return.")

                     except ValueError:
                         book_info_lines.append("- Return status could not be determined due to invalid delivery date.")


                elif book_expected_delivery_duration and book_expected_delivery_duration != 'N/A':
                     book_info_lines.append(f"- Expected Delivery Duration: {book_expected_delivery_duration}")
                # No specific fallback for individual books if both are missing


                book_details_list.append("\n".join(book_info_lines))

        if book_details_list:
             return "\n\n".join(book_details_list) # Separate details for each book with double newline
        else:
             return f"Could not find valid details for the specified book numbers in order {order_number}."