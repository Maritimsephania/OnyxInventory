from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .services.mpesa_service import MPesaService
from .models import Product, Category, Cart, CartItem, Sale, MPesaPayment
import logging

logger = logging.getLogger(__name__)

def index(request):
    return render(request, 'pos_app/index.html')

def pos_view(request):
    products = Product.objects.all()
    categories = Category.objects.all()
    return render(request, 'pos_app/pos.html', {
        'products': products,
        'categories': categories
    })

def get_cart(request):
    session_id = request.session.session_key
    if not session_id:
        request.session.create()
        session_id = request.session.session_key
    
    cart, created = Cart.objects.get_or_create(
        session_id=session_id,
        is_completed=False
    )
    return cart

@csrf_exempt
def add_to_cart(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        
        product = get_object_or_404(Product, id=product_id)
        cart = get_cart(request)
        
        # Check if item already in cart
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'price': product.price, 'quantity': quantity}
        )
        
        if not created:
            cart_item.quantity += quantity
            cart_item.save()
        
        return JsonResponse({'success': True, 'message': 'Product added to cart'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

def get_cart_items(request):
    cart = get_cart(request)
    items = []
    total = 0
    
    for item in cart.items.all():
        item_total = item.total()
        items.append({
            'id': item.id,
            'product': item.product.name,
            'price': float(item.price),
            'quantity': item.quantity,
            'total': float(item_total)
        })
        total += item_total
    
    return JsonResponse({
        'items': items,
        'total': float(total)
    })

@csrf_exempt
def remove_from_cart(request, item_id):
    cart = get_cart(request)
    CartItem.objects.filter(id=item_id, cart=cart).delete()
    return JsonResponse({'success': True})

@csrf_exempt
def checkout(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        payment_method = data.get('payment_method', 'cash')
        
        cart = get_cart(request)
        total = sum(item.total() for item in cart.items.all())
        
        # Create sale record
        sale = Sale.objects.create(
            cart=cart,
            total_amount=total,
            payment_method=payment_method
        )
        
        # Update stock
        for item in cart.items.all():
            product = item.product
            product.stock -= item.quantity
            product.save()
        
        # Mark cart as completed
        cart.is_completed = True
        cart.save()
        
        # Create new cart for session
        request.session.flush()
        request.session.create()
        
        return JsonResponse({
            'success': True,
            'sale_id': sale.id,
            'total': float(total)
        })
    
    return JsonResponse({'success': False})

@csrf_exempt
def initiate_mpesa_payment(request):
    """
    Initiate M-Pesa STK Push payment
    POST data: {
        "phone_number": "0712345678",
        "amount": 1500,
        "cart_id": 123,
        "reference": "POS Payment"
    }
    """
    if request.method == 'POST':
        try:
            # Parse JSON data
            try:
                data = json.loads(request.body.decode('utf-8'))
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid JSON data'
                }, status=400)
            
            # Extract and validate data
            phone_number = data.get('phone_number', '').strip()
            amount = data.get('amount')
            cart_id = data.get('cart_id')
            reference = data.get('reference', 'POS Payment')
            
            # Validate required fields
            if not phone_number:
                return JsonResponse({
                    'success': False,
                    'message': 'Phone number is required'
                }, status=400)
            
            if not amount:
                return JsonResponse({
                    'success': False,
                    'message': 'Amount is required'
                }, status=400)
            
            try:
                amount = float(amount)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'message': 'Amount must be a positive number'
                }, status=400)
            
            # Initialize M-Pesa service
            mpesa_service = MPesaService()
            
            # Generate reference if cart_id provided
            if cart_id:
                reference = f"POS{str(cart_id).zfill(6)}"
            
            # Initiate STK Push
            result = mpesa_service.initiate_stk_push(
                phone_number=phone_number,
                amount=amount,
                reference=reference,
                description="Payment for goods/services"
            )
            
            if result['success']:
                # Create payment record
                payment = MPesaPayment.objects.create(
                    phone_number=phone_number,
                    amount=amount,
                    checkout_request_id=result['checkout_request_id'],
                    merchant_request_id=result.get('merchant_request_id', ''),
                    status='pending'
                )
                
                # Try to link to cart/sale
                if cart_id:
                    try:
                        cart = Cart.objects.get(id=cart_id)
                        # Check if sale exists for this cart
                        try:
                            sale = Sale.objects.get(cart=cart)
                            payment.sale = sale
                            payment.save()
                        except Sale.DoesNotExist:
                            # Sale doesn't exist yet, that's OK
                            pass
                    except Cart.DoesNotExist:
                        # Cart doesn't exist, that's OK
                        pass
                
                logger.info(f"✅ Created MPesaPayment ID: {payment.id}")
                
                return JsonResponse({
                    'success': True,
                    'checkout_request_id': result['checkout_request_id'],
                    'customer_message': result.get('customer_message', 'Please check your phone'),
                    'payment_id': payment.id,
                    'message': 'Payment initiated successfully'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': result.get('error', 'Failed to initiate payment')
                }, status=400)
                
        except Exception as e:
            logger.error(f"❌ Error in initiate_mpesa_payment: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f'Server error: {str(e)}'
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'message': 'Only POST method allowed'
    }, status=405)

@csrf_exempt
def mpesa_callback(request):
    """
    Handle M-Pesa STK Push callback
    This is called by M-Pesa when payment is complete
    """
    if request.method == 'POST':
        try:
            # Parse callback data
            callback_data = json.loads(request.body.decode('utf-8'))
            logger.info(f"📞 Received M-Pesa callback: {json.dumps(callback_data, indent=2)}")
            
            # Extract callback details
            stk_callback = callback_data.get('Body', {}).get('stkCallback', {})
            checkout_request_id = stk_callback.get('CheckoutRequestID')
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')
            
            if not checkout_request_id:
                logger.error("❌ No CheckoutRequestID in callback")
                return JsonResponse({
                    "ResultCode": 1,
                    "ResultDesc": "Missing CheckoutRequestID"
                })
            
            # Find payment record
            try:
                payment = MPesaPayment.objects.get(checkout_request_id=checkout_request_id)
            except MPesaPayment.DoesNotExist:
                logger.error(f"❌ Payment not found for checkout ID: {checkout_request_id}")
                return JsonResponse({
                    "ResultCode": 1,
                    "ResultDesc": "Payment not found"
                })
            
            # Update payment based on result
            if result_code == 0:
                # Payment successful
                payment.status = 'successful'
                payment.result_code = str(result_code)
                payment.result_description = result_desc
                
                # Extract transaction details from callback metadata
                callback_metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
                for item in callback_metadata:
                    name = item.get('Name')
                    value = item.get('Value')
                    
                    if name == 'MpesaReceiptNumber':
                        payment.mpesa_receipt_number = str(value)
                    elif name == 'Amount':
                        payment.amount = float(value)
                    elif name == 'TransactionDate':
                        try:
                            # Convert M-Pesa timestamp (YYYYMMDDHHMMSS) to datetime
                            from datetime import datetime
                            trans_date = datetime.strptime(str(value), "%Y%m%d%H%M%S")
                            payment.transaction_date = trans_date
                        except:
                            pass
                
                payment.save()
                logger.info(f"✅ Payment successful: {payment.mpesa_receipt_number}")
                
                # If linked to a sale, you could update sale status here
                if payment.sale:
                    logger.info(f"✅ Linked to Sale ID: {payment.sale.id}")
                    # payment.sale.payment_status = 'paid'
                    # payment.sale.save()
                
            else:
                # Payment failed
                payment.status = 'failed'
                payment.result_code = str(result_code)
                payment.result_description = result_desc
                payment.save()
                logger.warning(f"❌ Payment failed: {result_desc}")
            
            # Always return success to M-Pesa
            return JsonResponse({
                "ResultCode": 0,
                "ResultDesc": "Success"
            })
            
        except json.JSONDecodeError:
            logger.error("❌ Invalid JSON in callback")
            return JsonResponse({
                "ResultCode": 1,
                "ResultDesc": "Invalid JSON"
            })
        except Exception as e:
            logger.error(f"❌ Error processing callback: {str(e)}")
            return JsonResponse({
                "ResultCode": 1,
                "ResultDesc": "Processing error"
            })
    
    return JsonResponse({
        "ResultCode": 1,
        "ResultDesc": "Invalid request method"
    })

def check_payment_status(request, checkout_request_id):
    """Check status of a payment"""
    try:
        payment = MPesaPayment.objects.get(checkout_request_id=checkout_request_id)
        
        return JsonResponse({
            'success': True,
            'status': payment.status,
            'receipt_number': payment.mpesa_receipt_number,
            'amount': float(payment.amount),
            'phone_number': payment.phone_number,
            'created_at': payment.created_at.isoformat(),
            'is_successful': payment.is_successful
        })
        
    except MPesaPayment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Payment not found'
        }, status=404)

def mpesa_payments_list(request):
    """List M-Pesa payments (for admin/testing)"""
    payments = MPesaPayment.objects.all().order_by('-created_at')[:50]
    
    data = []
    for payment in payments:
        data.append({
            'id': payment.id,
            'phone_number': payment.phone_number,
            'amount': float(payment.amount),
            'status': payment.status,
            'receipt_number': payment.mpesa_receipt_number,
            'checkout_request_id': payment.checkout_request_id,
            'created_at': payment.created_at.isoformat(),
            'is_successful': payment.is_successful
        })
    
    return JsonResponse({
        'success': True,
        'count': len(data),
        'payments': data
    })