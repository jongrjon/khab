from django.utils.encoding import force_str, force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.timezone import make_aware
from django.utils import timezone
from django.shortcuts import render
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.models import User, Group
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from datetime import datetime, date, time, timedelta
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.template import loader
from django.db.models import Sum, Count, Q, Subquery, OuterRef, IntegerField, Value, F
from django.db.models.functions import Coalesce
from .models import Product, Sale, Payment, Invite, UserProfile
from khab.inviteTokens import invite_token_generator
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
import csv
import json
import uuid

#Index view, Main Boutique. Requires login.
@login_required
def index(request):
    products = Product.objects.filter(active=True).annotate(salenum = Count('sale', distinct = True)).order_by("-salenum")
    template = loader.get_template('boutique/index.html')
    response ={}
    #Checks if signed in user is a personal account before preparing appropriate objects
    if request.user.groups.filter(name="person").exists():
        if request.method == "POST":       
            data = request.POST
            pid = data.get("purchase")
            bought = Product.objects.get(id = pid)
            if bought is not None:
                buy = Sale.objects.create(buyer = request.user, product = bought, price = bought.current_price, saletime = timezone.now())
                response = {'status' : "Success", 'message': "Þú keyptir "+ bought.name}
            else:
                response = {'status' : "Failed", 'message': "Kaupin tókust ekki, reyndu aftur. Ef vandamálið er viðvarandi hafðu samband við vefstjóra"}
        context = {
        'products' : products,
        'response' : response
        }
        return HttpResponse(template.render(context,request))
    #Vendor accounts are redirected to the new kiosk splash screen
    if request.user.groups.filter(name="vendor").exists():
        return HttpResponseRedirect('/vendor/')
    #Superuser is strictly for administration purposes, can not purchase. therefore redirected to product
    #management site.
    if request.user.is_superuser:
        return HttpResponseRedirect('/dashboard')
    #Redirects to login if no type of account is logged in.
    else:
        return HttpResponseRedirect('/login')

@login_required
def dashboard(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')
    template = loader.get_template('boutique/dashboard.html')
    today = date.today()
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    # Overall stats
    person_users = annotate_user_debt(
        User.objects.filter(groups__name='person', is_active=True)
    )
    total_debt = 0
    debtors = []
    for u in person_users:
        balance = u.total_paid - u.total_spent
        total_debt += balance
        if balance < 0:
            debtors.append({
                'id': u.id,
                'name': u.first_name + ' ' + u.last_name,
                'debt': balance,
            })
    debtors.sort(key=lambda u: u['debt'])

    # This month vs last month revenue
    this_month_sales = Sale.objects.filter(
        saletime__gte=this_month_start
    ).aggregate(
        count=Count('id'),
        revenue=Coalesce(Sum('price'), Value(0))
    )
    last_month_sales = Sale.objects.filter(
        saletime__gte=last_month_start,
        saletime__lt=this_month_start
    ).aggregate(
        count=Count('id'),
        revenue=Coalesce(Sum('price'), Value(0))
    )

    # Product trends (#10): this month vs last month per product
    this_month_products = dict(
        Sale.objects.filter(saletime__gte=this_month_start)
        .values_list('product__name')
        .annotate(cnt=Count('id'))
        .values_list('product__name', 'cnt')
    )
    last_month_products = dict(
        Sale.objects.filter(saletime__gte=last_month_start, saletime__lt=this_month_start)
        .values_list('product__name')
        .annotate(cnt=Count('id'))
        .values_list('product__name', 'cnt')
    )
    all_product_names = set(this_month_products.keys()) | set(last_month_products.keys())
    product_trends = []
    for name in all_product_names:
        if name is None:
            continue
        this_count = this_month_products.get(name, 0)
        last_count = last_month_products.get(name, 0)
        diff = this_count - last_count
        product_trends.append({
            'name': name,
            'this_month': this_count,
            'last_month': last_count,
            'diff': diff,
        })
    product_trends.sort(key=lambda p: p['this_month'], reverse=True)

    # Active users count
    active_users = User.objects.filter(groups__name='person', is_active=True).count()

    # Recent sales (last 10)
    recent_sales = Sale.objects.select_related('buyer', 'product').order_by('-saletime')[:10]

    context = {
        'total_debt': total_debt,
        'debtors': debtors[:10],
        'this_month': this_month_sales,
        'last_month': last_month_sales,
        'product_trends': product_trends,
        'active_users': active_users,
        'recent_sales': recent_sales,
        'today': today,
        'this_month_name': this_month_start.strftime('%B'),
        'last_month_name': last_month_start.strftime('%B'),
    }
    return HttpResponse(template.render(context, request))

#Personal status view. User can view their purchase history, their previous payments and current debit or credit.
@login_required
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
            # Purge expired invites
            from django.conf import settings

            expiry = timezone.now() - timedelta(seconds=settings.INVITE_TIMEOUT)
            Invite.objects.filter(timeout__lt=expiry).delete()
            invites = Invite.objects.all().order_by('invited')
            # Persons
            person_users = annotate_user_debt(
                User.objects.filter(groups__name='person').select_related('profile')
            )
            users = []
            for muser in person_users:
                profile = getattr(muser, 'profile', None)
                user = {
                    'id':muser.id,
                    'first_name' : muser.first_name,
                    'last_name' : muser.last_name,
                    'debt' : muser.total_paid - muser.total_spent,
                    'is_active' : muser.is_active,
                    'avatar_url' : profile.avatar_url if profile else None,
                    'initials' : (muser.first_name[:1] + muser.last_name[:1]).upper(),
                }
                users.append(user)
            users = sort_users_is(users, key_func=lambda u: u['first_name'])
            # Vendors
            vendors = list(User.objects.filter(groups__name='vendor').order_by('username'))
            context = {
                'users' : users,
                'vendors' : vendors,
                'invites' :invites,
            }
            return HttpResponse(template.render(context, request))
        else:
            user = User.objects.select_related('profile').get(id=id)
            purchase = Sale.objects.filter(buyer = user).select_related('product').order_by('-saletime')
            payment = Payment.objects.filter(payer = user).order_by('-paytime')
            debt = getdebt(user)
            profile = getattr(user, 'profile', None)
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
                'password': password,
                'avatar_url': profile.avatar_url if profile else None,
                'initials': (user.first_name[:1] + user.last_name[:1]).upper(),
                'total_purchases': purchase.count(),
                'total_payments': payment.count(),
                'total_spent': purchase.aggregate(Sum('price'))['price__sum'] or 0,
                'total_paid': payment.aggregate(Sum('amount'))['amount__sum'] or 0,
                'product_summary': Sale.objects.filter(buyer=user).values('product__name').annotate(
                    count=Count('id')
                ).order_by('-count'),
            }
            return HttpResponse(template.render(context,request))
    else:
        return HttpResponseRedirect('/')

#Admin view for managing sales, showing every unique sale as well as sales numbers for products
@login_required
def sales(request):

    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    show_all = request.GET.get('all', '')

    # Default to current month if no dates provided
    today = date.today()
    if show_all:
        start_date = datetime.min.date()
        end_date = datetime(year=9999, month=12, day=31, hour=0, minute=0, second=0)
    elif start_date_str and start_date_str != '':
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str and end_date_str != '':
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            end_date = datetime.combine(end_date, time.max).replace(tzinfo=None)
        else:
            end_date = datetime.combine(today, time.max).replace(tzinfo=None)
    else:
        start_date = today.replace(day=1)
        end_date = datetime.combine(today, time.max).replace(tzinfo=None)

    products = Product.objects.annotate(salenum = Count('sale', filter=Q(sale__saletime__gte=start_date, sale__saletime__lte=end_date), distinct = True)).order_by("-salenum")
    template = loader.get_template('boutique/sales.html')

    # Summary stats
    sales_qs = Sale.objects.filter(saletime__gte=start_date, saletime__lte=end_date)
    summary = sales_qs.aggregate(
        total_count=Count('id'),
        total_revenue=Sum('price')
    )
    top_product = products.first()

    # Quick filter dates
    from datetime import timedelta
    week_start = today - timedelta(days=today.weekday())

    context = {
        'products' : products,
        'start_date': start_date if isinstance(start_date, date) else start_date,
        'end_date': end_date.date() if hasattr(end_date, 'date') else end_date,
        'today': today,
        'week_start': week_start,
        'month_start': today.replace(day=1),
        'summary_count': summary['total_count'] or 0,
        'summary_revenue': summary['total_revenue'] or 0,
        'top_product': top_product.name if top_product and top_product.salenum > 0 else '-',
        'top_product_count': top_product.salenum if top_product else 0,
    }

    if request.user.is_superuser:
        sales_list = sales_qs.select_related('buyer', 'product').order_by('-saletime')
        paginator = Paginator(sales_list, 50)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        context['sales'] = page_obj
        context['page_obj'] = page_obj
        context['all_products'] = Product.objects.all().order_by('name')

    return HttpResponse(template.render(context, request))

def editsale(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            sid = data.get("saleid")
            amount = data.get("amount")
            product_id = data.get("product")
            Sale.objects.filter(id=sid).update(price=amount, product_id=product_id)
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
        active_products = Product.objects.filter(active=True).annotate(salenum = Count('sale', distinct = True)).order_by("-salenum")
        inactive_products = Product.objects.filter(active=False).annotate(salenum = Count('sale', distinct = True)).order_by("-salenum")
        context = {
        'active_products' : active_products,
        'inactive_products' : inactive_products,
        }
        if  request.method == "POST":
            data = request.POST
            pid = data.get("productid")
            img = request.FILES.get("productimage")
            pname = data.get("productname")
            if data.get("productactive") is None:
                pactive = False
            else:
                pactive = True
            if img is None:
                tempprod = Product.objects.get(id = pid)
                img = tempprod.prod_img
            pprice = data.get("productprice")
            offer_active = data.get("offertoggle") is not None
            offer_price = data.get("offerprice") or None
            Product.objects.update_or_create(id = pid, defaults = {'name' : pname,'prod_img' : img, 'price' : pprice, 'active' : pactive, 'offer_active': offer_active, 'offer_price': offer_price})
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
        payments = Payment.objects.select_related('payer').all().order_by('-paytime')
        modelusers = annotate_user_debt(
            User.objects.filter(groups__name__in = ['person'])
        )
        users = []
        for muser in modelusers:
            user = {
                'id':muser.id,
                'first_name' : muser.first_name,
                'last_name' : muser.last_name,
                'debt' : muser.total_paid - muser.total_spent
            }
            users.append(user)
        users = sort_users_is(users, key_func=lambda u: u['first_name'])
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
                Payment.objects.create(payer = user, amount = amnt, paytime = timezone.now())
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

@login_required
def scoreboard(request):
    template = loader.get_template('boutique/scoreboard.html')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    else:
        start_date = datetime.min.date()

    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        end_date = datetime.combine(end_date, time.max).replace(tzinfo=None)
    else:
        end_date = datetime(year=9999, month=12, day=31, hour=0, minute=0, second=0)

    # Single annotated query instead of N+1
    spent_subq = Sale.objects.filter(
        buyer=OuterRef('pk'),
        saletime__gte=start_date,
        saletime__lte=end_date
    ).values('buyer').annotate(s=Sum('price')).values('s')

    modelusers = User.objects.filter(
        groups__name='person', is_active=True
    ).annotate(
        total_spent=Coalesce(Subquery(spent_subq, output_field=IntegerField()), Value(0)),
        purchase_count=Count('sale', filter=Q(sale__saletime__gte=start_date, sale__saletime__lte=end_date)),
        unique_products=Count('sale__product', filter=Q(sale__saletime__gte=start_date, sale__saletime__lte=end_date), distinct=True),
    )

    biggest = 0
    users = []
    for muser in modelusers:
        spent = muser.total_spent
        if spent > biggest:
            biggest = spent
        if muser == request.user or request.user.is_superuser:
            name = muser.first_name + " " + muser.last_name
        else:
            name = "**********"
        users.append({
            'name': name,
            'sales': float(spent),
            'purchase_count': muser.purchase_count,
            'unique_products': muser.unique_products,
            'is_current': muser == request.user,
        })

    for user in users:
        if biggest > 0:
            user['pct'] = int(round(user['sales'] / biggest * 100, 0))
        else:
            user['pct'] = 0

    users.sort(key=lambda u: u['sales'], reverse=True)

    # Fun stats (#11) — product-based only to avoid leaking names
    stats = {}
    stats['total_purchases'] = sum(u['purchase_count'] for u in users)
    stats['total_revenue'] = int(sum(u['sales'] for u in users))
    # Most popular product in the period
    top_product = Sale.objects.filter(
        saletime__gte=start_date, saletime__lte=end_date
    ).values('product__name').annotate(
        cnt=Count('id')
    ).order_by('-cnt').first()
    if top_product and top_product['product__name']:
        stats['top_product'] = {'name': top_product['product__name'], 'count': top_product['cnt']}
    # Average purchase price
    if stats['total_purchases'] > 0:
        stats['avg_price'] = int(round(stats['total_revenue'] / stats['total_purchases']))

    context = {
        'users': users,
        'current': request.user.first_name + " " + request.user.last_name,
        'stats': stats,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    return HttpResponse(template.render(context, request))

def createinvite(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            email = data.get("email")
            Invite.objects.update_or_create(email = email, defaults = {'timeout' : timezone.now()})
            return HttpResponseRedirect('/payments')
    else:
        return HttpResponseRedirect('/')

def newinvite(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            email = data.get("email")
            if email is not None and not User.objects.filter(email = email).exists():
                Invite.objects.update_or_create(invited = email, defaults = {'timeout': timezone.now()})
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

def deleteinvite(request):
    if request.user.is_superuser:
        if request.method == "POST":
            data = request.POST
            invite_id = data.get("inviteid")
            Invite.objects.filter(id=invite_id).delete()
    return HttpResponseRedirect('/users')

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
                            previous ={
                                    'fn' : fn,
                                    'ln': ln
                            }
                            context = {
                                'invite' : invite,
                                'previous': previous,
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

def debtcsv(request):
    if request.user.is_superuser:
        response = HttpResponse(
            content_type='text/csv',
            headers={'Content-Disposition': 'attachment; filename="debt.csv"'},
        )
        response.write(u'\ufeff'.encode('utf8'))
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
        writer = csv.writer(response)
        for user in users:
            writer.writerow([str(user['first_name']+" "+user['last_name']), user['debt']])
        return response
    else:
        return HttpResponseRedirect('/')
    
def paymentscsv(request):
    if request.user.is_superuser:
        response = HttpResponse(
            content_type='text/csv',
            headers={'Content-Disposition': 'attachment; filename="payments.csv"'},
        )
        response.write(u'\ufeff'.encode('utf8'))
        payments = Payment.objects.all().order_by('-paytime')
        writer = csv.writer(response)
        for p in payments:
            print(p.paytime)
            writer.writerow([p.paytime.strftime("%d/%m/%Y, %H:%M"), str(p.payer.first_name+" "+p.payer.last_name), p.amount])
        return response
    else:
        return HttpResponseRedirect('/')

def salescsv(request):
    if request.user.is_superuser:
        response = HttpResponse(
            content_type='text/csv',
            headers={'Content-Disposition': 'attachment; filename="sales.csv"'},
        )
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        # Convert the start and end dates to datetime objects
        if start_date and start_date != '':
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = datetime.min.date()

        if end_date and end_date != '':
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            # Set the end date to the end of the day
            end_date = datetime.combine(end_date, time.max).replace(tzinfo=None)
        else:
            end_date = datetime(year=9999, month=12, day=31, hour=0, minute=0, second=0)
        products = Product.objects.annotate(salenum = Count('sale', filter=Q(sale__saletime__gte=start_date, sale__saletime__lte=end_date), distinct = True)).order_by("-salenum")
        response.write(u'\ufeff'.encode('utf8'))
        writer = csv.writer(response)
        writer.writerow([start_date.strftime("%m/%d/%Y")+" - ", end_date.strftime("%m/%d/%Y")])
        for p in products:
            writer.writerow([p.name, str(p.salenum)])
        return response
    else:
        return HttpResponseRedirect('/')   

####################VENDOR KIOSK VIEWS################################

def vendor_splash(request):
    if not request.user.groups.filter(name="vendor").exists():
        return HttpResponseRedirect('/')
    users_qs = User.objects.filter(
        groups__name='person', is_active=True
    ).select_related('profile')
    user_list = []
    for u in users_qs:
        profile = getattr(u, 'profile', None)
        avatar_url = profile.avatar_url if profile else None
        user_list.append({
            'id': u.id,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'avatar_url': avatar_url,
        })
    user_list = sort_users_is(user_list, key_func=lambda u: u['first_name'])
    template = loader.get_template('boutique/vendor_splash.html')
    context = {'users': user_list}
    return HttpResponse(template.render(context, request))

def vendor_shop(request, user_id):
    if not request.user.groups.filter(name="vendor").exists():
        return HttpResponseRedirect('/')
    buyer = User.objects.get(pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=buyer)
    # Products sorted by how often this specific user has bought them
    products = Product.objects.filter(active=True).annotate(
        user_salenum=Count('sale', filter=Q(sale__buyer=buyer)),
        salenum=Count('sale', distinct=True)
    ).order_by('-user_salenum', '-salenum')
    template = loader.get_template('boutique/vendor_shop.html')
    context = {
        'buyer': buyer,
        'buyer_avatar': profile.avatar_url,
        'products': products,
    }
    return HttpResponse(template.render(context, request))

def vendor_checkout(request):
    if not request.user.groups.filter(name="vendor").exists():
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    if request.method != "POST":
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        items = data.get('items', [])
        buyer = User.objects.get(pk=user_id)
        total = 0
        purchased = []
        txn = uuid.uuid4()
        now = timezone.now()
        for item in items:
            product = Product.objects.get(pk=item['product_id'])
            qty = int(item['quantity'])
            for _ in range(qty):
                Sale.objects.create(
                    buyer=buyer,
                    product=product,
                    price=product.current_price,
                    saletime=now,
                    transaction=txn,
                )
            total += product.current_price * qty
            purchased.append(f'{product.name} x{qty}')
        message = f'{buyer.first_name} {buyer.last_name} keypti: {", ".join(purchased)}'
        return JsonResponse({'status': 'success', 'message': message, 'total': total})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

####################HELPER FUNCTIONS##################################
# Icelandic alphabet sort order
IS_ALPHABET = 'AÁBCDÐEÉFGHIÍJKLMNOÓPQRSTUÚVWXYÝZÞÆÖaábcdðeéfghiíjklmnoópqrstuvwxyýzþæö'
IS_SORT_KEY = {c: i for i, c in enumerate(IS_ALPHABET)}

def is_sort_key(text):
    """Sort key function for Icelandic alphabetical order."""
    return [IS_SORT_KEY.get(c, 1000 + ord(c)) for c in text]

def sort_users_is(users, key_func=lambda u: u.first_name):
    """Sort a list of users/dicts by Icelandic alphabet."""
    return sorted(users, key=lambda u: is_sort_key(key_func(u)))

def annotate_user_debt(queryset):
    """Annotate a User queryset with total_paid, total_spent, and debt using subqueries.
    Must use Subquery — a plain Sum annotation across two relations causes a cross-join."""
    paid_subq = Payment.objects.filter(payer=OuterRef('pk')).values('payer').annotate(s=Sum('amount')).values('s')
    spent_subq = Sale.objects.filter(buyer=OuterRef('pk')).values('buyer').annotate(s=Sum('price')).values('s')
    return queryset.annotate(
        total_paid=Coalesce(Subquery(paid_subq, output_field=IntegerField()), Value(0)),
        total_spent=Coalesce(Subquery(spent_subq, output_field=IntegerField()), Value(0)),
    )

def gettotalexpenses(user, startdate=datetime.min.date(), enddate=datetime.max.date()):
        credit = Sale.objects.filter(buyer = user).filter(saletime__gte=startdate, saletime__lte=enddate).aggregate(Sum('price'))
        if credit.get('price__sum') is None:
            credit = 0
        else:
            credit = credit.get('price__sum')
        return credit

def getdebt(user):
        debit = Payment.objects.filter(payer = user).aggregate(Sum('amount'))
        if debit.get('amount__sum') is None:
            debit = 0
        else:
            debit = debit.get('amount__sum')
        debt = debit-gettotalexpenses(user)
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
