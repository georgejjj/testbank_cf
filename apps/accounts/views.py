import csv
import io
import secrets

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import LoginForm, BootstrapPasswordChangeForm, CSVImportForm
from .models import User


class CustomLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.must_change_password:
            return reverse_lazy('password_change')
        if user.is_instructor or user.is_ta:
            return reverse_lazy('instructor_dashboard')
        return reverse_lazy('student_dashboard')


class CustomPasswordChangeView(PasswordChangeView):
    form_class = BootstrapPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('student_dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.must_change_password = False
        self.request.user.save(update_fields=['must_change_password'])
        return response


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def student_roster(request):
    if not request.user.is_staff_role:
        return redirect('student_dashboard')

    students = User.objects.filter(role='STUDENT').order_by('last_name', 'first_name')
    form = CSVImportForm()

    if request.method == 'POST' and request.user.is_instructor:
        if 'csv_file' in request.FILES:
            form = CSVImportForm(request.POST, request.FILES)
            if form.is_valid():
                credentials = _import_students_csv(request.FILES['csv_file'])
                if credentials:
                    messages.success(request, f'Imported {len(credentials)} students.')
                    return _credential_csv_response(credentials)
                else:
                    messages.error(request, 'No students imported. Check CSV format.')

        elif 'reset_password' in request.POST:
            user_id = request.POST.get('user_id')
            try:
                student = User.objects.get(id=user_id, role='STUDENT')
                new_pw = f'{student.student_id}@Cf'
                student.set_password(new_pw)
                student.must_change_password = True
                student.save()
                messages.success(request, f'Password reset for {student.username}. New password: {new_pw}')
            except User.DoesNotExist:
                messages.error(request, 'Student not found.')

        elif 'delete_student' in request.POST:
            user_id = request.POST.get('user_id')
            User.objects.filter(id=user_id, role='STUDENT').delete()
            messages.success(request, 'Student removed.')

        return redirect('student_roster')

    return render(request, 'accounts/roster.html', {'students': students, 'form': form})


def _import_students_csv(csv_file):
    credentials = []
    decoded = csv_file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(decoded))

    for row in reader:
        username = row.get('username', '').strip()
        if not username:
            continue
        if User.objects.filter(username=username).exists():
            continue

        sid = row.get('student_id', '').strip()
        password = f'{sid}@Cf' if sid else f'{username}@Cf'
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=row.get('first_name', '').strip(),
            last_name=row.get('last_name', '').strip(),
            email=row.get('email', '').strip(),
            student_id=row.get('student_id', '').strip(),
            role='STUDENT',
            must_change_password=True,
        )
        credentials.append((username, password, user.get_full_name(), user.student_id))

    return credentials


def _credential_csv_response(credentials):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="student_credentials.csv"'
    writer = csv.writer(response)
    writer.writerow(['username', 'password', 'full_name', 'student_id'])
    for username, password, name, sid in credentials:
        writer.writerow([username, password, name, sid])
    return response
