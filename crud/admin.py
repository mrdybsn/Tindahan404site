from django.contrib import admin
from .models import Product, Category, Sale, SaleItem, Supplier, Purchase, PurchaseItem, StockAdjustment


# Register your models here.

admin.site.register(Product)
admin.site.register(Category)
admin.site.register(Sale)
admin.site.register(SaleItem)
admin.site.register(Supplier)
admin.site.register(Purchase)
admin.site.register(PurchaseItem)
admin.site.register(StockAdjustment)