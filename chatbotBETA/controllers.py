# controllers.py

import logging
import re
# Need to import services and repositories
from services import AIService, FormatterService
from repositories import OrderRepository # Order is also needed but already imported in repository through model

class ChatController:
    """
    Controller for chat-related logic, specifically handling Order and General FAQ intents.
    Book Recommendation intent is handled directly in app.py by calling BookRecommendationService.
    """

    # MODIFICATION: Added user_id parameter to handle authentication.
    @staticmethod
    def process_chat_message(latest_message, chat_history, user_id):
        """
        Handle user chat message for Order and General FAQ intents.
        Uses AI and provided context (order details, FAQs, chat history).

        Args:
            latest_message (str): The user's current query.
            chat_history (list): List of previous messages in the conversation.
            user_id (int): The ID of the logged-in user. 0 or None if not logged in.

        Returns:
            str: The bot's response. Can be prefixed with 'LOGIN_REQUIRED:'
        """

        # --- NEW AUTHENTICATION CHECK ---
        # If the user is not logged in, return a special response.
        # The calling code (app.py) should handle this to create the final JSON response.
        if not user_id or user_id == 0:
            return "LOGIN_REQUIRED: Please log in to view your order details."
        # --- END OF NEW AUTHENTICATION CHECK ---

        # Get logger instance within the function
        request_logger_available = 'request_activity' in logging.Logger.manager.loggerDict
        request_logger_instance = logging.getLogger('request_activity') if request_logger_available else None

        log_context_prefix = "chat history on" if chat_history and len(chat_history) > 0 else "general query"

        # Basic check, though app.py should handle empty messages
        if not latest_message or latest_message.strip() == "":
            if request_logger_instance:
                request_logger_instance.info(f"ChatController:process_chat_message: Received empty user input.")
            return "Oops! It seems your message vanished like a plot twist before it reached me. How can I help you with your Bookswagon order or a general question today?"

        # Note: Intent detection is now done in app.py before calling this controller.
        # This controller assumes the intent is either 'order' or 'general_faq'.

        is_hindi = AIService.detect_language(latest_message)

        # Format chat history for the AI API
        formatted_chat_history = []
        for msg in chat_history:
            role = 'user' if msg.get('sender') == 'user' else 'assistant'
            formatted_chat_history.append({'role': role, 'content': msg.get('message', '')})


        # --- Order ID Extraction Logic (kept for order intent) ---
        # Check current message first
        extracted_id = AIService.extract_order_id(latest_message)

        # If not found in current message, check chat history
        if not extracted_id:
            for msg_entry in reversed(chat_history): # Iterate through history in reverse
                if msg_entry.get('sender') == 'user': # Only consider user messages
                    history_order_id = AIService.extract_order_id(msg_entry.get('message', ''))
                    if history_order_id:
                        extracted_id = history_order_id
                        logging.info(f"ChatController:process_chat_message: Found order ID in chat history: {extracted_id}")
                        if request_logger_instance:
                            request_logger_instance.info(f"Request: {log_context_prefix}: Found order ID in chat history: {extracted_id}")
                        break # Found the most recent, break out

        order_context = None

        if extracted_id:
            # MODIFICATION: Pass the user_id to the fetch method for a secure check.
            order = OrderRepository.fetch_order_by_id(extracted_id, user_id)
            if order:
                order_context = order
                logging.info(f"ChatController:process_chat_message: Found and using order context for: {extracted_id} for user {user_id}")
                if request_logger_instance:
                    request_logger_instance.info(f"Request: {log_context_prefix}: Found and using order context for: {extracted_id} for user {user_id}")
            else:
                # MODIFICATION: Updated response to be more generic and secure.
                logging.info(f"ChatController:process_chat_message: Invalid order ID or access denied for order {extracted_id} and user {user_id}")
                if request_logger_instance:
                    request_logger_instance.info(f"Request: {log_context_prefix}: Invalid order ID or access denied for order {extracted_id} and user {user_id}")
                response = AIService.get_response_in_language(
                    f"I couldn't find any order with ID {extracted_id} associated with your account. Please check the order number and try again.", is_hindi)
                return response # Return early if order not found


        response = "" # Initialize response

        # --- Logic based on Order Context and User Query ---

        # Check for explicit request for full details
        detail_keywords = ["details", "more information", "tell me more", "give me details", "what are the details", "full info"]
        if order_context and any(keyword in latest_message.lower() for keyword in detail_keywords):
             logging.info(f"ChatController:process_chat_message: User asked for detailed order info for found order.")
             if request_logger_instance:
                 request_logger_instance.info(f"Request: {log_context_prefix}: User asked for detailed order info for found order.")
             response = FormatterService.format_order_response(order_context)

        # Check for specific book indices within an order
        # Regex looks for numbers potentially separated by commas or spaces
        elif order_context and order_context.books and len(order_context.books) > 0 and re.search(r'\b\d+(?:(?:,|\s)+\d+)*\b', latest_message):
            total_books = len(order_context.books)
            indices = FormatterService.parse_book_indices(latest_message, total_books)
            if indices:
                logging.info(f"ChatController:process_chat_message: User asked about specific books: {indices} for found order.")
                if request_logger_instance:
                    request_logger_instance.info(f"Request: {log_context_prefix}: User asked about specific books: {indices} for found order.")
                response = FormatterService.format_specific_books_response(order_context, indices)
            else:
                 logging.info(f"ChatController:process_chat_message: User input contains numbers, but not valid book indices. Using AI for order context.")
                 if request_logger_instance:
                     request_logger_instance.info(f"Request: {log_context_prefix}: User input contains numbers, but not valid book indices. Using AI for order context.")
                 # Fallback to general AI summary if numbers don't match book indices
                 response = AIService.generate_order_summary(order_context, latest_message, is_hindi, formatted_chat_history)


        # Check for exit commands
        elif any(cmd in latest_message.lower() for cmd in AIService.EXIT_COMMANDS):
            logging.info(f"ChatController:process_chat_message: User initiated exit.")
            if request_logger_instance:
                request_logger_instance.info(f"Request: {log_context_prefix}: User initiated exit.")
            # Generate a polite closing response using AI
            ai_prompt = """
            The user has indicated they want to end the conversation (e.g., by saying 'exit', 'bye', or 'thank you').
            Generate a polite and friendly closing response as a Bookswagon assistant named Vidya.
            """
            messages = [
                {"role": "system", "content": "You are a helpful customer service assistant for Bookswagon named Vidya."},
                *formatted_chat_history[-4:], # Include a few recent messages for context
                {"role": "user", "content": latest_message}
            ]
            raw_ai_response = AIService.query_deepseek(messages, temperature=0.7)
            response = AIService.get_response_in_language(raw_ai_response, is_hindi)
            if request_logger_instance:
                request_logger_instance.info(f"Request: {log_context_prefix}: Bot response (exit): {response}")
            return response # Return the exit response immediately


        # If order context exists but no specific detail/book request, use AI for order summary
        elif order_context:
             logging.info(f"ChatController:process_chat_message: Using AI for order summary/general query within found order context.")
             if request_logger_instance:
                 request_logger_instance.info(f"Request: {log_context_prefix}: Using AI for order summary/general query within found order context.")
             response = AIService.generate_order_summary(order_context, latest_message, is_hindi, formatted_chat_history)

        # If no order context, use AI for general response (which might ask for order number)
        else:
             logging.info(f"ChatController:process_chat_message: Using AI for general response/asking for order number.")
             if request_logger_instance:
                 request_logger_instance.info(f"Request: {log_context_prefix}: Using AI for general response/asking for order number.")
             response = AIService.generate_general_response(latest_message, is_hindi, formatted_chat_history)


        # Log the final response before returning
        if request_logger_instance:
            request_logger_instance.info(f"ChatController:process_chat_message: Bot response: {response}")

        return response
