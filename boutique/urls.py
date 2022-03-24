from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('products', views.products, name='products'),
    path('newproduct/<int:pnr>', views.newproduct, name='newproduct'),
    path('newproduct', views.newproduct, name='newproduct'),
    path('deleteproduct', views.deleteproduct, name='deleteproduct'),
    path('users', views.users, name='users'),
    path('users/<int:id>',views.users, name='users'),
    path('newpayment',views.newpayment, name='newpayment'),
]
