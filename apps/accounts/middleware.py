from django.shortcuts import redirect


class ForcePasswordChangeMiddleware:
    """Redirect users who must change their password."""

    EXEMPT_URLS = ['login', 'logout', 'password_change']
    EXEMPT_PATHS = ['/accounts/login/', '/accounts/logout/', '/accounts/password-change/', '/admin/']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.must_change_password:
            # Check by URL name
            url_name = ''
            if request.resolver_match:
                url_name = request.resolver_match.url_name or ''

            # Check by path as fallback
            path = request.path

            if url_name not in self.EXEMPT_URLS and not any(path.startswith(p) for p in self.EXEMPT_PATHS):
                return redirect('password_change')

        return self.get_response(request)
