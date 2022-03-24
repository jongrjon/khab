def populate_models(sender, **kwargs):
    from django.contrib.auth.models import User, Group, Permission

    # create groups
    person, created = Group.objects.get_or_create(name='person')
    vendor, created = Group.objects.get_or_create(name='vendor')
    # assign permissions to groups
   # add_sale = Permission.objects.get(name ='Can add sale')
   # view_sale = Permission.objects.get(name ='Can view sale')
   # view_payment = Permission.objects.get(name ='Can view payment')
   # view_product = Permission.objects.get(name ='Can view product')
   # view_user = Permission.objects.get(name ='Can view user')

   # person.permissions.add(add_sale)
   # person.permissions.add(view_sale)
   # person.permissions.add(view_payment)
   # person.permissions.add(view_product)
   # vendor.permissions.add(add_sale)
   # person.permissions.add(view_product)
   #::: person.permissions.add(view_user)
