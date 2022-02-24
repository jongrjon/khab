from django.shortcuts import render
from datetime import datetime
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from django.db.models import Sum
from .models import Product, Sale, Payment


def index(request):
    products = Product.objects.all()
    template = loader.get_template('boutique/index.html')
    context = {
        'products' : products,
    }
    if request.user.is_authenticated:
        if request.method == "POST":       
            data = request.POST
            pid = data.get("purchase")
            bought = Product.objects.get(id = pid)
            if bought is not None:
                buy = Sale.objects.create(buyer = request.user, product = bought, price = bought.price, saletime = datetime.now())
        return HttpResponse(template.render(context,request))
    else:
        return HttpResponseRedirect('/login')

def status(request):
    user = request.user
    purchase = Sale.objects.filter(buyer = user)
    debit = Sale.objects.filter(buyer = user).aggregate(Sum('price'))
    print(debit)
    if debit.get('price__sum') is None:
        debit = 0
    else:
        debit = debit.get('price__sum')
    credit = Payment.objects.filter(payer = user).aggregate(Sum('amount'))
    if credit.get('amount__sum') is None:
        credit = 0
    else:
        credit = credit.get('amount__sum')
    print(debit)
    print(credit)
    debt = credit-debit
    template = loader.get_template('boutique/status.html')
    context = {
        'user' : user,
        'purchase' :purchase,
        'debt' : debt,
    }
    return HttpResponse(template.render(context,request))
