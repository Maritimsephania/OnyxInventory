from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Product, Cart, CartItem, Sale, StockMovement, Supplier, MPesaPayment

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_count', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']
    
    def product_count(self, obj):
        return obj.product_set.count()
    product_count.short_description = 'Product Count'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'stock', 'status_display', 'updated_at']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'sku', 'barcode']
    list_editable = ['price', 'stock']  # Can edit directly in list view
    readonly_fields = ['created_at', 'updated_at', 'status_display']
    
    # Add these fields to the form
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'sku', 'barcode', 'category', 'description')
        }),
        ('Pricing', {
            'fields': ('cost_price', 'price')
        }),
        ('Inventory', {
            'fields': ('stock', 'min_stock_level', 'max_stock_level')
        }),
        ('Status', {
            'fields': ('is_active', 'status_display')
        }),
    )
    
    # Custom method to show colored status
    def status_display(self, obj):
        colors = {
            'out_of_stock': 'red',
            'low_stock': 'orange',
            'in_stock': 'green'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.status_display
        )
    status_display.short_description = 'Status'

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['product', 'movement_type', 'quantity', 'created_at', 'created_by']
    list_filter = ['movement_type', 'created_at']
    search_fields = ['product__name', 'reason']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'  # Adds date navigation at top

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['id', 'total_amount', 'payment_method', 'created_at']
    list_filter = ['payment_method', 'created_at']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

# Optionally register Cart and CartItem if you want to manage them in admin
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'session_id', 'is_completed', 'created_at']
    list_filter = ['is_completed', 'created_at']
    readonly_fields = ['created_at']

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'quantity', 'price', 'total']
    list_filter = ['product__category']
    
    def total(self, obj):
        return obj.total()
    total.short_description = 'Total'

# Register Supplier if you have the model
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email', 'phone']
    search_fields = ['name', 'contact_person']

@admin.register(MPesaPayment)
class MPesaPaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'phone_number', 'formatted_amount', 'status_display', 
                    'mpesa_receipt_number', 'created_at', 'sale_link']
    list_filter = ['status', 'created_at']
    search_fields = ['phone_number', 'mpesa_receipt_number', 'checkout_request_id']
    readonly_fields = ['created_at', 'updated_at', 'transaction_date', 'result_description']
    
    def formatted_amount(self, obj):
        return f"KES {int(obj.amount):,}"
    formatted_amount.short_description = 'Amount'
    formatted_amount.admin_order_field = 'amount'
    
    def status_display(self, obj):
        colors = {
            'pending': 'orange',
            'successful': 'green',
            'failed': 'red',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def sale_link(self, obj):
        if obj.sale:
            return format_html(
                '<a href="/admin/pos_app/sale/{}/change/">Sale #{}</a>',
                obj.sale.id,
                obj.sale.id
            )
        return "-"
    sale_link.short_description = 'Linked Sale'