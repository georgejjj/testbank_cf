from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home_redirect(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_instructor:
        return redirect('instructor_dashboard')
    return redirect('student_dashboard')


@login_required
def help_page(request):
    return render(request, 'help.html')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_redirect, name='home'),
    path('help/', help_page, name='help'),
    path('accounts/', include('accounts.urls')),
    path('questions/', include('questions.urls')),
    path('assignments/', include('assignments.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
