from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages

class AdminAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/') and not request.path.startswith('/admin/login'):
            if not request.user.is_authenticated:
                messages.error(request, 'Please log in to access the admin area.')
                return redirect('crud:admin_login')
            elif not request.user.role == 'admin':
                messages.error(request, 'You do not have permission to access the admin area.')
                return redirect('crud:landing_page')

        response = self.get_response(request)
        return response 