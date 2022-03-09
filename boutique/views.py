from django.shortcuts import render
from django.contrib.auth.models import User, Group
from datetime import datetime
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from django.db.models import Sum
from .models import Product, Sale, Payment


def index(request):
    products = Product.objects.all()
    template = loader.get_template('boutique/index.html')
    users = User.objects.filter(groups__name='person')
    response ={}
    
    if request.user.groups.filter(name="person").exists():
        if request.method == "POST":       
            data = request.POST
            pid = data.get("purchase")
            bought = Product.objects.get(id = pid)
            if bought is not None:
                buy = Sale.objects.create(buyer = request.user, product = bought, price = bought.price, saletime = datetime.now())
                response = {'status' : "Success", 'message': "Þú keyptir "+ bought.name}
            else:
                response = {'status' : "Failed", 'message': "Kaupin tókust ekki, reyndu aftur. Ef vandamálið er viðvarandi hafðu samband við vefstjóra"}
        context = {
        'products' : products,
        'response' : response
        }
        return HttpResponse(template.render(context,request))
    if request.user.groups.filter(name="vendor").exists():
        
        if request.method == "POST":       
            data = request.POST
            pid = data.get("purchase")
            uid = data.get("buyer")
            user = User.objects.get(pk = uid)
            bought = Product.objects.get(id = pid)
            if bought is not None and user is not None:
                buy = Sale.objects.create(buyer = user, product = bought, price = bought.price, saletime = datetime.now())
                response = {'status' : "Success", 'message': user.first_name+ " "+user.last_name+" keypti "+bought.name}
                print(user.first_name)
            else:
                response = {'status' : "Failed", 'message': "Kaupin tókust ekki, reyndu aftur. Ef vandamálið er viðvarandi hafðu samband við vefstjóra"}
        context = {
        'products' : products,
        'users' :users,
        'response' : response,
        }
        return HttpResponse(template.render(context,request))
    if request.user.is_superuser:
        return HttpResponseRedirect('/products')
    else:
        return HttpResponseRedirect('/login')

def status(request):
    if request.user.groups.filter(name="person").exists():
        user = request.user
        purchase = Sale.objects.filter(buyer = user)
        debit = Sale.objects.filter(buyer = user).aggregate(Sum('price'))
        if debit.get('price__sum') is None:
            debit = 0
        else:
            debit = debit.get('price__sum')
        credit = Payment.objects.filter(payer = user).aggregate(Sum('amount'))
        if credit.get('amount__sum') is None:
            credit = 0
        else:
            credit = credit.get('amount__sum')
        debt = credit-debit
        template = loader.get_template('boutique/status.html')
        context = {
            'user' : user,
            'purchase' :purchase,
            'debt' : debt,
        }
        return HttpResponse(template.render(context,request))
    else:
        return HttpResponseRedirect('/')

def products(request):
    if request.user.is_superuser:
        template = loader.get_template('boutique/products.html')
        products = products = Product.objects.all()
        context = {
        'products' :products,
        }
        if  request.method == "POST":
            data = request.POST
            img = request.FILES.get("productimage")
            pname = data.get("productname")
            pprice = data.get("productprice")
            Product.objects.update_or_create(name = pname, defaults ={'name' : pname,'prod_img' : img, 'price' : pprice})
        return HttpResponse(template.render(context,request))
    else:
        return HttpResponseRedirect('/')
