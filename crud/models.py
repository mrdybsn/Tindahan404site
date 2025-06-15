from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('inventory_manager', 'Inventory Manager'),
        ('cashier', 'Cashier'),
    ]
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    password_reset_token = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
    def __str__(self):
        return self.username

class Category(models.Model):
    category_name = models.CharField(max_length=100, unique=True)
    category_description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        verbose_name = "Product Category"
        verbose_name_plural = "Product Categories"
    def __str__(self):
        return self.category_name

class Product(models.Model):
    product_id = models.BigAutoField(primary_key=True, blank=False)
    product_name = models.CharField(max_length=200, blank=False)
    product_description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock = models.IntegerField(default=0)  # Main stock field
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    minimum_stock_level = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ['product_name']

    def __str__(self):
        return self.product_name

    def get_profit_margin(self):
        if self.cost_price is not None and self.price > 0:
            return ((self.price - self.cost_price) / self.price) * 100
        return 0

    def is_low_stock(self):
        return self.stock <= self.minimum_stock_level

    def formatted_price(self):
        return f"${self.price:.2f}"

class Sale(models.Model):
    cashier = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction_date = models.DateTimeField(auto_now_add=True, db_column='date')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(max_length=10, blank=True)  # 'amount' or 'percent'
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def __str__(self):
        return f"Sale #{self.id} - {self.transaction_date.strftime('%Y-%m-%d %H:%M')}"

    def calculate_discount_amount(self):
        subtotal = sum(item.subtotal for item in self.items.all())
        if self.discount_type == 'percent':
            return subtotal * (self.discount_value / Decimal('100'))
        return self.discount_value

    def calculate_vat(self, net_total):
        settings = SystemSettings.get_settings()
        vat_rate = settings.tax_rate or Decimal('0.00')
        return (net_total * vat_rate / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def calculate_totals(self):
        if not self.pk:  # If this is a new sale without a primary key
            return {
                'subtotal': Decimal('0'),
                'discount': Decimal('0'),
                'vat': self.vat_amount,
                'final_total': self.total_amount
            }
            
        subtotal = sum(item.subtotal for item in self.items.all())
        discount = self.calculate_discount_amount()
        net_total = subtotal - discount
        vat = self.calculate_vat(net_total)
        final_total = net_total + vat
        return {
            'subtotal': subtotal,
            'discount': discount,
            'vat': vat,
            'final_total': final_total
        }

    def save(self, *args, **kwargs):
        if not kwargs.pop('skip_calculations', False):
            totals = self.calculate_totals()
            self.vat_amount = totals['vat']
            self.total_amount = totals['final_total']
        super().save(*args, **kwargs)

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField()
    unit_price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    class Meta:
        verbose_name = "Sale Item"
        verbose_name_plural = "Sale Items"
    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_price_at_sale
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.quantity} x {self.product.product_name if self.product else 'Deleted Product'} in Sale #{self.sale.id}"

# --- Supplier and Purchase Management (for Restocking) ---

class Supplier(models.Model):
    company_name = models.CharField(max_length=200, unique=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        ordering = ['company_name']

    def __str__(self):
        return self.company_name


class Purchase(models.Model):
    purchase_date = models.DateTimeField(auto_now_add=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='purchases')
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='purchases_received')
    status = models.CharField(max_length=50, choices=(
        ('pending', 'Pending'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled')
    ), default='pending')
    expected_delivery = models.DateField(null=True, blank=True)
    stock_updated = models.BooleanField(default=False)  # New field to track stock updates
    
    class Meta:
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"
        ordering = ['-purchase_date']

    def __str__(self):
        return f"PO #{self.id} from {self.supplier.company_name if self.supplier else 'N/A'} - {self.status}"

class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField()
    unit_cost_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal_cost = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        # Calculate subtotal before saving
        self.subtotal_cost = self.quantity * self.unit_cost_at_purchase
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product.product_name if self.product else 'Deleted Product'} for PO #{self.purchase.id}"

class SystemSettings(models.Model):
    company_name = models.CharField(max_length=255)
    company_address = models.TextField()
    company_phone = models.CharField(max_length=50)
    company_email = models.EmailField()
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    currency_symbol = models.CharField(max_length=5, default='$')
    low_stock_threshold = models.IntegerField(default=10)
    enable_email_notifications = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    def save(self, *args, **kwargs):
        if not self.pk:
            existing_settings = SystemSettings.objects.first()
            if existing_settings:
                self.pk = existing_settings.pk
        super(SystemSettings, self).save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        return cls.objects.first() or cls.objects.create(
            company_name='My Company',
            company_address='Company Address',
            company_phone='123-456-7890',
            company_email='company@example.com'
        )

class StockAdjustment(models.Model):
    ADJUSTMENT_TYPES = [
        ('count', 'Stock Count'),
        ('damage', 'Damage'),
        ('return', 'Return'),
        ('other', 'Other')
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_adjustments')
    adjustment_type = models.CharField(max_length=10, choices=ADJUSTMENT_TYPES, default='count')
    quantity_change = models.IntegerField(default=0)
    reason = models.TextField(default='')
    date = models.DateTimeField(auto_now_add=True)
    adjusted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name = "Stock Adjustment"
        verbose_name_plural = "Stock Adjustments"
    
    def __str__(self):
        return f"{self.adjustment_type} - {self.product.product_name} ({self.quantity_change:+d})"
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Only update stock on creation
            self.product.stock += self.quantity_change
            if self.product.stock < 0:
                raise ValueError("Stock quantity cannot be negative")
            self.product.save()
        super().save(*args, **kwargs)

class DailyOrderCounter(models.Model):
    date = models.DateField(unique=True)
    counter = models.IntegerField(default=0)
    last_reset = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['date']),
        ]

    @classmethod
    def get_or_create_counter(cls, date=None):
        if date is None:
            date = timezone.now().date()
        counter, created = cls.objects.get_or_create(date=date)
        return counter

    @classmethod
    def increment_counter(cls, date=None):
        if date is None:
            date = timezone.now().date()
        counter = cls.get_or_create_counter(date)
        counter.counter += 1
        counter.save()
        return counter.counter

    @classmethod
    def get_current_count(cls, date=None):
        if date is None:
            date = timezone.now().date()
        counter = cls.get_or_create_counter(date)
        return counter.counter

    @classmethod
    def reset_counter(cls, date=None):
        if date is None:
            date = timezone.now().date()
        counter = cls.get_or_create_counter(date)
        counter.counter = 0
        counter.save()
        return counter