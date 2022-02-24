from django.db import models
from django.contrib.auth.models import User

class Product(models.Model):
	name = models.CharField(max_length=50)
	prod_img = models.ImageField(upload_to='images/products/')
	price = models.IntegerField()

	def __str__(self):
		return self.name

class Sale(models.Model):
	buyer = models.ForeignKey(User, on_delete = models.PROTECT)
	product = models.ForeignKey(Product, on_delete = models.PROTECT)
	price = models.IntegerField()
	saletime = models.DateTimeField('date published')

	def __str__(self):
		return "%s : %s" % (self.buyer, self.product)

class Payment(models.Model):
	payer = models.ForeignKey(User, on_delete = models.PROTECT)
	amount = models.IntegerField()
	paytime = models.DateTimeField('date transfered')

	def __str__(self):
		return "%s : %s" % (self.payer, self.amount)

