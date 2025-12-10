import requests
import base64
import json
from datetime import datetime
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class MPesaService:
    """Custom M-Pesa service for STK Push"""
    
    def __init__(self):
        self.config = settings.MPESA_CONFIG
        self.environment = self.config['ENVIRONMENT']
        
        # Set API endpoints based on environment
        if self.environment == 'sandbox':
            self.base_url = "https://sandbox.safaricom.co.ke"
        else:
            self.base_url = "https://api.safaricom.co.ke"
        
        self.access_token = None
        self.token_expiry = None
    
    def _get_auth_string(self):
        """Create Basic Auth string"""
        auth_string = f"{self.config['CONSUMER_KEY']}:{self.config['CONSUMER_SECRET']}"
        return base64.b64encode(auth_string.encode()).decode()
    
    def get_access_token(self):
        """Get OAuth access token from M-Pesa"""
        try:
            url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
            headers = {
                'Authorization': f'Basic {self._get_auth_string()}'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            self.access_token = data['access_token']
            self.token_expiry = timezone.now() + timezone.timedelta(seconds=3500)
            
            logger.info("✅ M-Pesa access token obtained")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to get M-Pesa token: {str(e)}")
            raise Exception(f"Failed to connect to M-Pesa: {str(e)}")
    
    def _ensure_token(self):
        """Ensure we have a valid token"""
        if not self.access_token or not self.token_expiry or timezone.now() >= self.token_expiry:
            return self.get_access_token()
        return self.access_token
    
    def _generate_password(self):
        """Generate M-Pesa API password"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        data = f"{self.config['SHORTCODE']}{self.config['PASSKEY']}{timestamp}"
        password = base64.b64encode(data.encode()).decode()
        return password, timestamp
    
    def format_phone_number(self, phone):
        """Format phone number to 2547XXXXXXXX format"""
        # Remove any spaces or special characters
        phone = ''.join(filter(str.isdigit, str(phone)))
        
        # Convert to 254 format
        if phone.startswith('0'):
            return '254' + phone[1:]
        elif phone.startswith('254'):
            return phone
        elif len(phone) == 9 and phone.startswith('7'):
            return '254' + phone
        else:
            raise ValueError(f"Invalid phone number format: {phone}")
    
    def initiate_stk_push(self, phone_number, amount, reference="POS Payment", description="Goods/Services"):
        """
        Initiate STK Push payment
        
        Args:
            phone_number (str): Customer phone number
            amount (int): Amount in KES
            reference (str): Payment reference
            description (str): Transaction description
            
        Returns:
            dict: Response data
        """
        try:
            # Validate amount
            amount = int(float(amount))
            if amount < 1:
                raise ValueError("Amount must be at least KES 1")
            
            # Format phone number
            formatted_phone = self.format_phone_number(phone_number)
            
            # Get access token
            token = self._ensure_token()
            
            # Generate password
            password, timestamp = self._generate_password()
            
            # Prepare payload
            payload = {
                "BusinessShortCode": self.config['SHORTCODE'],
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": amount,
                "PartyA": formatted_phone,
                "PartyB": self.config['SHORTCODE'],
                "PhoneNumber": formatted_phone,
                "CallBackURL": self.config['CALLBACK_URL'],
                "AccountReference": reference[:12],  # Max 12 chars
                "TransactionDesc": description[:13]   # Max 13 chars
            }
            
            # Make API request
            url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"📱 Initiating STK Push: {formatted_phone} - KES {amount:,}")
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Check response
            if data.get('ResponseCode') == '0':
                logger.info(f"✅ STK Push initiated: {data.get('CustomerMessage')}")
                return {
                    'success': True,
                    'checkout_request_id': data.get('CheckoutRequestID'),
                    'merchant_request_id': data.get('MerchantRequestID'),
                    'customer_message': data.get('CustomerMessage'),
                    'response_code': data.get('ResponseCode'),
                    'response_description': data.get('ResponseDescription')
                }
            else:
                logger.error(f"❌ STK Push failed: {data.get('ResponseDescription')}")
                return {
                    'success': False,
                    'error': data.get('ResponseDescription'),
                    'response_code': data.get('ResponseCode')
                }
                
        except ValueError as e:
            logger.error(f"❌ Validation error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Network error: {str(e)}")
            return {
                'success': False,
                'error': f"Network error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }