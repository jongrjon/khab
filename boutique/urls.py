from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('editsale', views.editsale, name='editsale'),
    path('deletesale',views.deletesale, name='deletesale'),
    path('sales', views.sales, name='sales'),
    path('products', views.products, name='products'),
    path('newproduct/<int:pnr>', views.newproduct, name='newproduct'),
    path('newproduct', views.newproduct, name='newproduct'),
    path('deleteproduct', views.deleteproduct, name='deleteproduct'),
    path('users', views.users, name='users'),
    path('users/<int:id>',views.users, name='users'),
    path('newpayment',views.newpayment, name='newpayment'),
    path('editpayment', views.editpayment, name='editpayment'),
    path('deletepayment', views.deletepayment, name='deletepayment'),
    path('payments', views.payments, name='payments'),
    path(r'^register/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
                views.Register.AsView(), name='register'),
]
