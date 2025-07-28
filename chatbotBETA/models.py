# models.py
from datetime import datetime

class OrderBook:
    """Model for a book in an order"""

    def __init__(self, product_name, isbn=None, tracking_number=None,
                 delivery_date=None, delivery_status=None, expected_delivery_duration=None):
        self.product_name = product_name
        self.isbn = isbn
        self.tracking_number = tracking_number
        self.delivery_date = delivery_date
        self.delivery_status = delivery_status
        self.expected_delivery_duration = expected_delivery_duration

    def format_date(self, date):
        """Format date for display"""
        if isinstance(date, datetime):
            return date.strftime("%d/%m/%Y")
        return date if date else 'N/A'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'product_name': self.product_name,
            'isbn': self.isbn,
            'tracking_number': self.tracking_number,
            'delivery_date': self.format_date(self.delivery_date),
            'delivery_status': self.delivery_status,
            'expected_delivery_duration': self.expected_delivery_duration
        }


class Order:
    """Model for an order"""

    def __init__(self, order_number, order_summary_id=None, purchase_date=None,
                 promise_date=None, order_status=None, cancellation_reason=None,
                 payment_status=None, order_amount=None, customer_email=None, # Added order_amount
                 customer_name=None, shipping_address=None, shipping_city=None,
                 shipping_country=None, shipping_state=None, shipping_zip=None,
                 shipping_mobile=None, tracking_number=None, shipping_carrier=None,
                 tracking_url=None, shipment_status=None, shipping_date=None):
        self.order_number = order_number
        self.order_summary_id = order_summary_id
        self.purchase_date = purchase_date
        self.promise_date = promise_date
        self.order_status = order_status
        self.cancellation_reason = cancellation_reason
        self.payment_status = payment_status
        self.order_amount = order_amount # Initialize order_amount
        self.customer_email = customer_email
        self.customer_name = customer_name
        self.shipping_address = shipping_address
        self.shipping_city = shipping_city
        self.shipping_country = shipping_country
        self.shipping_state = shipping_state
        self.shipping_zip = shipping_zip
        self.shipping_mobile = shipping_mobile
        self.tracking_number = tracking_number
        self.shipping_carrier = shipping_carrier
        self.tracking_url = tracking_url
        self.shipment_status = shipment_status
        self.shipping_date = shipping_date


        self.books = []

    def add_book(self, book):
        """Add a book to the order"""
        self.books.append(book)

    def format_date(self, date):
        """Format date for display"""
        if isinstance(date, datetime):
            return date.strftime("%d/%m/%Y")
        return date if date else 'N/A'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'order_details': {
                'order_number': self.order_number,
                'order_summary_id': self.order_summary_id,
                'purchase_date': self.format_date(self.purchase_date),
                'promise_date': self.format_date(self.promise_date),
                'order_status': self.order_status,
                'cancellation_reason': self.cancellation_reason,
                'payment_status': self.payment_status,
                'order_amount': self.order_amount, # Include order_amount in dict
                'customer_email': self.customer_email,
                'customer_name': self.customer_name,
                'shipping_address': self.shipping_address,
                'shipping_city': self.shipping_city,
                'shipping_country': self.shipping_country,
                'shipping_state': self.shipping_state,
                'shipping_zip': self.shipping_zip,
                'shipping_mobile': self.shipping_mobile,
                'tracking_number': self.tracking_number,
                'shipping_carrier': self.shipping_carrier,
                'tracking_url': self.tracking_url,
                'shipment_status': self.shipment_status,
                'date_shipped': self.format_date(self.shipping_date),
            },
            'books': [book.to_dict() for book in self.books]
        }