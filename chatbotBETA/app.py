import os
import logging
import json
import pyodbc
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, g
from flask import send_from_directory
from werkzeug.exceptions import BadRequest

# New Imports for refactored classes and new services
from config import Config
from models import OrderBook, Order # Keeping for completeness
from repositories import OrderRepository, FaqRepository
from services import AIService, FormatterService
from controllers import ChatController
from book_service import BookRecommendationService # Import book_service (assuming this is the correct filename now)

# --- Configure Logging ---
# Get the absolute path of the directory where app.py is located
base_dir = os.path.dirname(os.path.abspath(__file__))
# Define the path for the new 'logs' directory
log_dir = os.path.join(base_dir, 'logs')
# Create the 'logs' directory if it doesn't exist
os.makedirs(log_dir, exist_ok=True)
# Define the full path to the log file
log_file_path = os.path.join(log_dir, 'requests.log')

logging.basicConfig(
    filename=log_file_path, # Use the new, full path
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

request_logger = logging.getLogger('request_activity')
request_logger.setLevel(logging.INFO)

try:
    request_handler = logging.FileHandler('log_file_path')
    request_formatter = logging.Formatter('%(filename)s:%(funcName)s: %(message)s')
    request_handler.setFormatter(request_formatter)
    request_logger.addHandler(request_handler)
    logging.info("app.py:Logging Setup: Request activity logger configured successfully.")
except Exception as e:
    logging.error(f"app.py:Logging Setup: Failed to configure request activity logger: {e}")

load_dotenv()

# Database Connection Management for all services that need a cursor
def get_db():
    """Get database connection and cursor, managed by Flask's g"""
    if 'db' not in g:
        conn_str = Config.get_connection_string()
        if not conn_str:
            logging.error("Database Connection:get_db: Database connection string is not configured.")
            g.db = None
            g.cursor = None
            return None, None

        try:
            g.db = pyodbc.connect(conn_str)
            g.cursor = g.db.cursor()
            logging.info("Database Connection:get_db: Database connection established.")
        except Exception as e:
            logging.error(f"Database Connection:get_db: Database connection error: {e}", exc_info=True)
            g.db = None
            g.cursor = None

    return g.db, g.cursor

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Routes
@app.route('/')
def index():
    """Render chat interface"""
    logging.info("app.py:index: Index page loaded.")
    if 'request_activity' in logging.Logger.manager.loggerDict:
        request_logger.info("Request: Index page loaded.")
    else:
        logging.error("app.py:index: Request activity logger not available.")

    return render_template('index.html')

@app.route('/api/message', methods=['POST'])
def chat():
    """Chat API endpoint - processes message based on detected intent"""
    logging.info(f"app.py:chat: Received message request.")
    logging.info("logging of request started")
    logging.info(f"Raw Data: {request.get_data()}")
    logging.info("logging of request ended")

    data = None
    try:
        data = request.get_json(silent=False)
    except BadRequest as e:
        logging.warning(f"app.py:chat: JSON parsing failed with UTF-8, trying alternate encoding: {e}")
        try:
            raw_data_str = request.data.decode('latin-1')
            data = json.loads(raw_data_str)
            logging.info("app.py:chat: Successfully parsed JSON with 'latin-1' decoding.")
        except Exception as decode_e:
            logging.error(f"app.py:chat: Failed to decode and parse JSON with alternate encoding: {decode_e}")
            return jsonify({'response': "Uh oh! It seems my digital dictionary got a bit scrambled trying to read your message. Could you try sending it again, perhaps in simpler terms?"}), 400

    if not data:
        logging.error("app.py:chat: No JSON data received or parsed successfully.")
        return jsonify({'response': "My apologies, it seems I received an empty scroll! I need a message to get started. What bookish quest can I help you with?"}), 400

    latest_message = data.get('message', '')
    chat_history = data.get('chat_history', [])
    # --- MODIFICATION: Get the userId from the request ---
    user_id = data.get('userId', 0) # Default to 0 if not provided

    if not latest_message or latest_message.strip() == "":
         response = "It seems silence fills the air! I didn't get your message. How can I help you navigate our bookshelves today?"
         logging.info(f"app.py:chat: Empty message received. Response: {response}")
         return jsonify({'response': response})

    formatted_chat_history = []
    for msg in chat_history:
        role = 'user' if msg.get('sender') == 'user' else 'assistant'
        formatted_chat_history.append({'role': role, 'content': msg.get('message', '')})

    user_intent = AIService.detect_user_intent(latest_message, formatted_chat_history)
    logging.info(f"app.py:chat: AI-detected intent: {user_intent}")
    if 'request_activity' in logging.Logger.manager.loggerDict:
        request_logger.info(f"Request: User query: '{latest_message}', AI-detected intent: {user_intent}")
    else:
        logging.error("app.py:chat: Request activity logger not available.")

    bot_response = "Hmm, I didn’t quite catch that. Want to try asking in a different way?"

    try:
        if user_intent == 'recommend_books':
            logging.info("app.py:chat: Routing to Book Recommendation Service.")
            # Ensure the cursor is passed correctly
            _, cursor = get_db() # Get the cursor from Flask's g object
            if cursor:
                bot_response = BookRecommendationService.recommend_books(latest_message, cursor)
            else:
                bot_response = "Oops! Our book shelf is a bit jammed right now. Try your recommendation request again in a moment!"
                logging.error("app.py:chat: Database cursor not available for book recommendation processing.")
            
        elif user_intent == 'order':
             logging.info(f"app.py:chat: Routing to Chat Controller for order intent.")
             _, cursor = get_db()
             if cursor:
                 # --- MODIFICATION: Pass the userId to the controller ---
                 bot_response = ChatController.process_chat_message(latest_message, chat_history, user_id)
             else:
                 bot_response = "Looks like our order scroll is temporarily misplaced. Can you check back in a little while?"
                 logging.error("app.py:chat: Database cursor not available for order processing.")

        elif user_intent == 'general_faq' or user_intent == 'unknown':
             logging.info(f"app.py:chat: Routing to Chat Controller for general_faq/unknown intent.")
             is_hindi = AIService.detect_language(latest_message)
             bot_response = AIService.generate_general_response(latest_message, is_hindi, formatted_chat_history)

    except Exception as e:
        logging.error(f"app.py:chat: An error occurred while processing message with AI-detected intent {user_intent}: {e}", exc_info=True)
        bot_response = (f"Yikes! Something unexpected happened behind the scenes. We’ll fix it faster than you can say ‘bestseller’ — please try again!")

    if 'request_activity' in logging.Logger.manager.loggerDict:
        request_logger.info(f"Request: Bot response: {bot_response}")
    else:
        logging.error("app.py:chat: Request activity logger not available.")

    # --- MODIFICATION: Handle the LOGIN_REQUIRED response from the controller ---
    if isinstance(bot_response, str) and bot_response.startswith("LOGIN_REQUIRED:"):
        # If the controller says login is required, create the specific JSON response.
        actual_message = bot_response.replace("LOGIN_REQUIRED: ", "")
        return jsonify({"action_required": "login", "response": actual_message})
    else:
        # Otherwise, return the normal response.
        return jsonify({'response': bot_response or "Our book-finding magic fizzled out for a moment. Mind giving it another try?"})


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection on request end"""
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
            logging.info("Database Connection:close_connection: Database connection closed.")
        except Exception as e:
            logging.error(f"Database Connection:close_connection: Error closing database connection: {e}")

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(host='0.0.0.0', port=1234, debug=debug)
