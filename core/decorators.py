from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib import messages

def superuser_required(view_func):
    """Decorator to restrict access to superusers only"""
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
    return wrapper

# Alternative: Using Django's built-in decorator
def superuser_required_alt(view_func):
    """Alternative using Django's user_passes_test"""
    return user_passes_test(lambda u: u.is_superuser)(view_func)
