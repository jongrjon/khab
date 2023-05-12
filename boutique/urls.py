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
    path('newinvite',views.newinvite, name='newinvite'),
    path('register/<uidb64>/<token>/', views.register, name='register'),
    path('noregister', views.noregister, name='noregister'),
    path('paymentscsv', views.paymentscsv, name='paymentscsv'),
    path('debtcsv', views.debtcsv, name='debtcsv'),
    path('scoreboard', views.scoreboard, name='scoreboard'),
]
