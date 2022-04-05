from django.utils.encoding import force_str, force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.shortcuts import render
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.models import User, Group
from django.contrib.auth import login
from datetime import datetime
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from django.db.models import Sum, Count
from .models import Product, Sale, Payment, Invite
from khab.inviteTokens import invite_token_generator
from django.core.mail import EmailMultiAlternatives


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
    if request.user.is_superuser or (request.user.groups.filter(name="person").exists() and request.user.id == id):
        if id is None and request.user.is_superuser:
            if request.method == "POST":
                data = request.POST
                uid = data.get('userid')
                changinguser = User.objects.get(id=uid)
                if changinguser.is_active is True:
                    changinguser.is_active = False
                    changinguser.save()
                else:
                    changinguser.is_active = True
                    changinguser.save()
            template = loader.get_template('boutique/users.html')
            invites = Invite.objects.all().order_by('invited')
            modelusers = User.objects.filter(groups__name__in=['person','vendor'])
            users = []
            for muser in modelusers:
                user = {
                    'id':muser.id,
                    'first_name' : muser.first_name,
                    'last_name' : muser.last_name,
                    'debt' : getdebt(muser),
                    'is_active' : muser.is_active
                }
                users.append(user)
            context = {
                'users' : users,
                'invites' :invites,
            }
            return HttpResponse(template.render(context, request))
        else:
            user = User.objects.get(id =id)
            purchase = Sale.objects.filter(buyer = user)
            payment = Payment.objects.filter(payer = user)
            debt = getdebt(user)
            template = loader.get_template('boutique/status.html')
            password = False
            if request.user.id == user.id:
                password = True
            if request.method == "POST":
                data = request.POST
                user.first_name = data.get('fn')
                user.last_name = data.get('ln')
                user.save()
            context = {
                'user' : user,
                'purchase' :purchase,
                'debt' : debt,
                'payment': payment,
                'password': password
            }
            return HttpResponse(template.render(context,request))
    else:
        return HttpResponseRedirect('/')

#Admin view for managing sales, showing every unique sale as well as sales numbers for products
def sales(request):
    if request.user.is_superuser:
        template = loader.get_template('boutique/sales.html')
        sales = Sale.objects.all().order_by('-saletime')
        products = Product.objects.annotate(salenum = Count('sale', distinct = True))
        context = {
            'sales' : sales,
            'products' : products,
        }
        return HttpResponse(template.render(context, request))
    else:
        return HttpResponseRedirect('/')

def editsale(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            sid = data.get("saleid")
            amount = data.get("amount")
            Sale.objects.filter(id = sid).update(price = amount)
            return HttpResponseRedirect('/sales')
    return HttpResponseRedirect("/")

def deletesale(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            sid = data.get("deletesale")
            Sale.objects.filter(id = sid).delete()
            return HttpResponseRedirect('/sales')
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
            Product.objects.update_or_create(id = pid, defaults = {'name' : pname,'prod_img' : img, 'price' : pprice})
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
            Product.objects.filter(id = pid).delete()
    return HttpResponseRedirect("/")

def payments(request):
    if request.user.is_superuser:
        template =loader.get_template('boutique/payments.html')
        payments = Payment.objects.all().order_by('-paytime')
        modelusers = User.objects.filter(groups__name__in = ['person']).order_by('first_name')
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
            'payments' : payments,
            'users' : users,
            }
        return HttpResponse(template.render(context, request))
    else:
        return HttpResponseRedirect('/')

def newpayment(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            uid = data.get("payerid")
            amnt =data.get("amount")
            nxt = data.get("previous_page")
            user = User.objects.get(id = uid)
            if user is not None:
                Payment.objects.create(payer = user, amount = amnt, paytime = datetime.now())
            return HttpResponseRedirect(nxt)
    else:
        return HttpResponseRedirect("/")

def editpayment(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            pid = data.get("paymentid")
            amount = data.get("amount")
            Payment.objects.filter(id = pid).update(amount = amount)
            return HttpResponseRedirect('/payments')
    else:
        return HttpResponseRedirect("/")

def deletepayment(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            pid = data.get("deletepayment")
            Payment.objects.filter(id = pid).delete()
            return HttpResponseRedirect('/payments')
    else:
        return HttpResponseRedirect('/')

def createinvite(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            email = data.get("email")
            Invite.objects.update_or_create(email = email, defaults = {'timeout' : datetime.now()})
            return HttpResponseRedirect('/payments')
    else:
        return HttpResponseRedirect('/')

def newinvite(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            email = data.get("email")
            if email is not None and not User.objects.filter(email = email).exists():
                Invite.objects.update_or_create(invited = email, defaults = {'timeout': datetime.now()})
                invite = Invite.objects.get(invited = email)
                currentSite = get_current_site(request)
                siteName = currentSite.name
                domain = currentSite.domain
                context = {
                    'email': email,
                    'domain': domain,
                    'siteName': siteName,
                    'uid': urlsafe_base64_encode(force_bytes(invite.pk)),
                    'token': invite_token_generator.make_token(invite),
                    'protocol': 'http',
                }
                subject = "Skráning í KHA Boutique"
                body = loader.render_to_string('registration/invite_email.html', context)
                from_email = None
                emailMessage = EmailMultiAlternatives(subject, body, from_email, [email])
                emailMessage.send()
                
        return HttpResponseRedirect('/users')
    else:
        return HttpResponseRedirect('/')

INVITE_RESET_SESSION_TOKEN = "_invite_token"

def register(request, **kwargs):
    reset_url_token = "registration"
    if "uidb64" in kwargs and "token" in kwargs:
        validLink = False
        invite = getinvite(kwargs["uidb64"])
        if invite is not None:
            token = kwargs["token"]
            if token == reset_url_token:
                session_token = request.session.get(INVITE_RESET_SESSION_TOKEN)
                if invite_token_generator.check_token(invite, session_token):
                    if request.method =="POST":
                        data = request.POST
                        username = data.get('username')
                        pw1 = data.get('password1')
                        pw2 = data.get('password2')
                        fn = data.get('firstname')
                        ln = data.get('lastname')
                        if pw1 == pw2:
                            user = User.objects.create_user(username = username, email = username, password = pw1, first_name = fn, last_name = ln)
                            group = Group.objects.get(name='person')
                            group.user_set.add(user)
                            login(request, user)
                            Invite.objects.filter(invited=username).delete()
                            return HttpResponseRedirect('/users/' +str(user.id))
                        else:
                            context = {
                                'invite' : invite,
                                'error' : "Lykilorðin sem þú settir inn eru ekki þau sömu"
                            }
                            template = loader.get_template('registration/register.html')
                            return HttpResponse(template.render(context, request))

                    else:
                        # If the token is valid, display the password reset form.
                        context = {'invite' : invite}
                        template = loader.get_template('registration/register.html')
                        return HttpResponse(template.render(context, request))
                else:
                    return HttpResponseRedirect('/noregister')
            else:
                if invite_token_generator.check_token(invite, token):
                    # Store the token in the session and redirect to the
                    # password reset form at a URL without the token. That
                    # avoids the possibility of leaking the token in the
                    # HTTP Referer header.
                    request.session[INVITE_RESET_SESSION_TOKEN] = token
                    redirect_url = request.path.replace(
                        token, reset_url_token
                    )
                    return HttpResponseRedirect(redirect_url)
                else:
                    return HttpResponseRedirect('/noregister')
        else:
            return HttpResponseRedirect('/noregister')
    else:
        return HttpResponseRedirect('/')

def noregister(request):
    template = loader.get_template('registration/registration_broken_link.html')
    context = {}
    return HttpResponse(template.render(context, request))    

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

def getinvite(uidb64):
        try:
            iid = urlsafe_base64_decode(uidb64).decode()
            invite = Invite.objects.get(pk=iid)
        except (
            TypeError,
            ValueError,
            OverflowError,
            Invite.DoesNotExist,
        ):
            invite = None
        return invite
