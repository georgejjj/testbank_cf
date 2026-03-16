from django.shortcuts import redirect


class ForcePasswordChangeMiddleware:
    """Redirect users who must change their password."""

    EXEMPT_URLS = ['login', 'logout', 'password_change']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.must_change_password:
            url_name = request.resolver_match.url_name if request.resolver_match else ''
            if url_name not in self.EXEMPT_URLS:
                return redirect('password_change')
        return self.get_response(request)
