from django.contrib import admin
from .models import Product, Sale, Payment, Invite, UserProfile

admin.site.register(Product)
admin.site.register(Sale)
admin.site.register(Payment)
admin.site.register(Invite)
admin.site.register(UserProfile)
