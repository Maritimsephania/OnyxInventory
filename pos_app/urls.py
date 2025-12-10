from django.urls import path
from . import views 

urlpatterns = [
    path('', views.index, name='index'),
    path('pos/', views.pos_view, name='pos'),
    path('api/add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('api/cart-items/', views.get_cart_items, name='get_cart_items'),
    path('api/remove-from-cart/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('api/checkout/', views.checkout, name='checkout'),
    path('api/mpesa/initiate/', views.initiate_mpesa_payment, name='initiate_mpesa'),
    path('api/mpesa/callback/', views.mpesa_callback, name='mpesa_callback'),
    path('api/mpesa/status/<str:checkout_request_id>/', views.check_payment_status, name='check_mpesa_status'),
    path('api/mpesa/payments/', views.mpesa_payments_list, name='mpesa_payments_list'),
]