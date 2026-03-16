from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'role', 'student_id']
    list_filter = ['role']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Testbank', {'fields': ('role', 'student_id', 'must_change_password')}),
    )
