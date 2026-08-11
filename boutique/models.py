import uuid
from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
	profile_img = models.ImageField(upload_to='images/avatars/', blank=True, null=True)

	def __str__(self):
		return self.user.get_full_name()

	@property
	def avatar_url(self):
		if self.profile_img:
			return self.profile_img.url
		return None

class Product(models.Model):
	name = models.CharField(max_length=50)
	prod_img = models.ImageField(upload_to='images/products/')
	price = models.IntegerField()
	active = models.BooleanField(default=True)
	offer_active = models.BooleanField(default=False)
	offer_price = models.IntegerField(null=True, blank=True)

	@property
	def current_price(self):
		if self.offer_active and self.offer_price is not None:
			return self.offer_price
		return self.price

	def __str__(self):
		return self.name

class Sale(models.Model):
	buyer = models.ForeignKey(User, on_delete = models.CASCADE)
	product = models.ForeignKey(Product, on_delete = models.SET_NULL, null=True)
	price = models.IntegerField()
	saletime = models.DateTimeField('date published')
	transaction = models.UUIDField(default=uuid.uuid4, db_index=True)

	class Meta:
		indexes = [
			models.Index(fields=['buyer', 'product']),
			models.Index(fields=['saletime']),
		]

	def __str__(self):
		return "%s : %s" % (self.buyer, self.product)

class Payment(models.Model):
	payer = models.ForeignKey(User, on_delete = models.CASCADE)
	amount = models.IntegerField()
	paytime = models.DateTimeField('date transfered')

	def __str__(self):
		return "%s : %s" % (self.payer, self.amount)

class Invite(models.Model):
	invited = models.CharField(max_length=50)
	timeout = models.DateTimeField('invite timeout')

	def __str__(self):
		return self.invited
