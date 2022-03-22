from django.shortcuts import render
from django.contrib.auth.models import User, Group
from datetime import datetime
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from django.db.models import Sum
from .models import Product, Sale, Payment

#Index view, Main Boutique. Requires login.
def index(request):
    products = Product.objects.all()
    template = loader.get_template('boutique/index.html')
    users = User.objects.filter(groups__name='person')
    response ={}
    #Checks if signed in user is a personal account before preparing appropriate objects
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
    #Checks if non personal account is a vending display account.
    #Prepares sales menu with a list of registered buyers.
    if request.user.groups.filter(name="vendor").exists():
        print("I get here")
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
    #Superuser is strictly for administration purposes, can not purchase. therefore redirected to product
    #management site.
    if request.user.is_superuser:
        return HttpResponseRedirect('/products')
    #Redirects to login if no type of account is logged in.
    else:
        return HttpResponseRedirect('/login')

#Personal status view. User can view their purchase history, their previous payments and current debit or credit.
def users(request, id = None):
    #Checks if logged in account is indeed marked as a person.
    print(type(request.user.id))
    if request.user.is_superuser or (request.user.groups.filter(name="person").exists() and request.user.id == id):
        if id is None and request.user.is_superuser:
            template = loader.get_template('boutique/users.html')
            modelusers = User.objects.filter(groups__name__in=['person','vendor'])
            users = []
            for muser in modelusers:
                user = {
                    'id':muser.id,
                    'first_name' : muser.first_name,
                    'last_name' : muser.last_name,
                    'debt' : getdebt(muser)
                }
                users.append(user)
            context = {
                'users' : users,
            }
            return HttpResponse(template.render(context, request))
        else:
            user = User.objects.get(id =id)
            purchase = Sale.objects.filter(buyer = user)
            payment = Payment.objects.filter(payer = user)
            debt = getdebt(user)
            template = loader.get_template('boutique/status.html')
            context = {
                'user' : user,
                'purchase' :purchase,
                'debt' : debt,
            }
            return HttpResponse(template.render(context,request))
    else:
        return HttpResponseRedirect('/')

#Admin view for managing products. Add, edit or remove products from the store. 
def products(request):
    if request.user.is_superuser:
        template = loader.get_template('boutique/products.html')
        products = products = Product.objects.all()
        context = {
        'products' :products,
        }
        if  request.method == "POST":
            data = request.POST
            pid = data.get("productid")
            img = request.FILES.get("productimage")
            pname = data.get("productname")
            if img is None:
                tempprod = Product.objects.get(id = pid)
                img = tempprod.prod_img
            pprice = data.get("productprice")
            Product.objects.update_or_create(id = pid, defaults ={'name' : pname,'prod_img' : img, 'price' : pprice})
        return HttpResponse(template.render(context,request))
    else:
        return HttpResponseRedirect('/')

#Modal view displayed inside the Product view for adding or editing products.
def newproduct(request,pnr = None):
    if request.user.is_superuser:
        template = loader.get_template('boutique/newproduct.html')
        context = {}
        if(pnr is not None):
            product = Product.objects.get(id = pnr)
            context = {
            'product' : product,
            }
        return HttpResponse(template.render(context, request))
    else:
        return HttpResponseRedirect('/')

#Non-render view used to accept POST request from newproduct when deleting a product.
#Only accepts POST requests from Admin user.
def deleteproduct(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            pid = data.get("deleteproduct")
            Product.objects.filter(id=pid).delete()
    return HttpResponseRedirect("/")

####################HELPER FUNCTIONS##################################
def getdebt(user):
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
        return debt
