from django.db import models
from django.contrib.auth.models import User
# Create your models here.
class Company(models.Model):
    company_name = models.CharField(max_length=150, null=True)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='company_owner')
    landline = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=20, null=True)
    address = models.TextField(null=True)
    email = models.EmailField(max_length=150)
    logo = models.ImageField(upload_to='static/media/%Y/%m/%d', blank=True,)
    
    def __str__(self):
        return self.company_name
    
    class Meta:
        verbose_name_plural = 'Company'
   
   
    