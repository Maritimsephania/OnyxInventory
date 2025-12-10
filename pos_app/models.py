from django.db import models
from django.utils import timezone

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def product_count(self):
        return self.product_set.count()
    
    @property
    def total_stock(self):
        return self.product_set.aggregate(total=models.Sum('stock'))['total'] or 0

class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    barcode = models.CharField(max_length=50, unique=True, blank=True, null=True)
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="SKU")
    description = models.TextField(blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    min_stock_level = models.IntegerField(default=10, verbose_name="Minimum Stock")
    max_stock_level = models.IntegerField(default=100, verbose_name="Maximum Stock")
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} (Stock: {self.stock})"
    
    @property
    def status(self):
        """Determine product stock status"""
        if self.stock <= 0:
            return 'out_of_stock'
        elif self.stock <= self.min_stock_level:
            return 'low_stock'
        else:
            return 'in_stock'
        

    @property
    def status_display(self):
        """Human readable status"""
        status_map = {
            'out_of_stock': 'Out of Stock',
            'low_stock': 'Low Stock',
            'in_stock': 'In Stock'
        }
        return status_map.get(self.status, 'Unknown')
    
    @property
    def stock_value(self):
        """Total value of current stock (cost price * quantity)"""
        return self.cost_price * self.stock
    
    @property
    def margin(self):
        """Profit margin"""
        if self.cost_price > 0:
            return ((self.price - self.cost_price) / self.cost_price) * 100
        return 0
    
    def add_stock(self, quantity, reason="", user=None):
        """Add stock to inventory"""
        old_stock = self.stock
        self.stock += quantity
        self.save()

        StockMovement.objects.create(
            product=self,
            movement_type='in',
            quantity=quantity,
            previous_quantity=old_stock,
            new_quantity=self.stock,
            reason=reason,
            created_by=user
        )

        return self.stock 
    

    def remove_stock(self, quantity, reason="", user=None):
        """Remove stock from inventory (for sales)"""
        if quantity > self.stock:
            raise ValueError(f"Cannot remove {quantity} items. Only {self.stock} available.")
        
        old_stock = self.stock
        self.stock -= quantity
        self.save()
        
        # Create stock movement record
        StockMovement.objects.create(
            product=self,
            movement_type='out',
            quantity=quantity,
            previous_quantity=old_stock,
            new_quantity=self.stock,
            reason=reason,
            created_by=user
        )
        
        return self.stock
    
    def set_stock(self, new_quantity, reason="", user=None):
        """Set stock to specific quantity"""
        old_stock = self.stock
        difference = new_quantity - old_stock
        
        self.stock = new_quantity
        self.save()
        
        # Create stock movement record
        movement_type = 'adjustment'
        StockMovement.objects.create(
            product=self,
            movement_type=movement_type,
            quantity=abs(difference),
            previous_quantity=old_stock,
            new_quantity=self.stock,
            reason=f"{reason} (Adjustment: {difference:+d})",
            created_by=user
        )
        
        return self.stock
    
class StockMovement(models.Model):
    """Track all inventory movements"""
    MOVEMENT_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
        ('return', 'Customer Return'),
        ('damage', 'Damaged Goods'),
        ('expired', 'Expired Goods'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
    
    def __str__(self):
        return f"{self.product.name} - {self.get_movement_type_display()} ({self.quantity})"
    
    @property
    def movement_sign(self):
        """Return + or - sign for quantity display"""
        if self.movement_type in ['in', 'return']:
            return '+'
        elif self.movement_type in ['out', 'damage', 'expired']:
            return '-'
        else:
            return '±'
        

class Supplier(models.Model):
    """Supplier information for restocking"""
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name

class PurchaseOrder(models.Model):
    """Purchase orders for restocking"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(blank=True, null=True)
    received_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-order_date']
    
    def __str__(self):
        return f"PO-{self.order_number}"
    
    @property
    def total_cost(self):
        return sum(item.total_cost for item in self.items.all())
    
    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items.all())

class PurchaseOrderItem(models.Model):
    """Items in a purchase order"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    received_quantity = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['purchase_order', 'product']
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity}"
    
    @property
    def total_cost(self):
        return self.quantity * self.unit_cost
    
    @property
    def is_fully_received(self):
        return self.received_quantity >= self.quantity

class Cart(models.Model):
    session_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def total(self):
        return self.quantity * self.price

class Sale(models.Model):
    cart = models.OneToOneField(Cart, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, choices=[
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile', 'Mobile Payment')
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Sale #{self.id} - ${self.total_amount}"


class MPesaPayment(models.Model):
    """Track M-Pesa STK Push payments"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('successful', 'Successful'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Link to sale (optional - can be added later)
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Customer information
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=0)
    
    # M-Pesa transaction details
    checkout_request_id = models.CharField(max_length=100, unique=True)
    merchant_request_id = models.CharField(max_length=100, blank=True)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True)
    transaction_date = models.DateTimeField(null=True, blank=True)
    
    # Status tracking
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    result_code = models.CharField(max_length=10, blank=True)
    result_description = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'M-Pesa Payment'
        verbose_name_plural = 'M-Pesa Payments'
    
    def __str__(self):
        return f"M-Pesa: {self.phone_number} - KES {int(self.amount):,}"
    
    @property
    def is_successful(self):
        return self.status == 'successful'
    
    @property
    def formatted_amount(self):
        return f"KES {int(self.amount):,}"