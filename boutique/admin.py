from django.contrib import admin
from .models import Product, Sale, Payment

admin.site.register(Product)
admin.site.register(Sale)
admin.site.register(Payment)

