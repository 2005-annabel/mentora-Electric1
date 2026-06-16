from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Q

from core.models import Product, Cart, CartItem, Category, Favorite

def _cart_count(request):
    if not request.user.is_authenticated:
        return 0
    total = CartItem.objects.filter(cart__user=request.user).aggregate(total=Sum('quantity'))['total']
    return total or 0


# ----------------------
# HOME & STATIC PAGES
# ----------------------

def home(request):
    products = Product.objects.all()[:8] # ← always defined first
    categories = Category.objects.all()

    # 🔍 SEARCH
    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    # 🏷 CATEGORY FILTER
    category = request.GET.get('category', 'all') or 'all'  # ← 'or all' guards against empty string
    if category == 'featured':
        products = products.filter(is_featured=True)
    elif category == 'new':
        products = products.filter(is_new=True)
    elif category == 'out-of-stock':
        products = products.filter(in_stock=False)
    elif category != 'all':
        products = products.filter(category__slug=category)
    # if category == 'all' → no filter, show everything ✓

    # 🔄 SORT
    sort = request.GET.get('sort', '') or ''  # ← guards against None
    sort_map = {
        'name-asc':   'name',
        'name-desc':  '-name',
        'price-low':  'price',
        'price-high': '-price',
    }
    if sort in sort_map:
        products = products.order_by(sort_map[sort])

        # Favourites
    user_favourites = []
    favourite_products = []
    if request.user.is_authenticated:
        user_favourites = list(
            Favorite.objects.filter(user=request.user).values_list('product_id', flat=True)
        )
        favourite_products = Product.objects.filter(
            id__in=user_favourites
        ).select_related('category')

    return render(request, 'index.html', {
        'products': products,
        'categories': categories,
        'current_category': category,
        'current_sort': sort,
        'current_query': query,
        'cart_count': _cart_count(request),
        'user_favourites': user_favourites,           # ← list of IDs for heart toggle
        'favourite_products': favourite_products,
    })

   


def about(request):
    return render(request, 'about.html')


def add_to_cart(request, product_id):
    if not request.user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Please sign in to add items to cart.'}, status=401)
        messages.error(request, 'Please sign in to add items to cart.')
        return redirect('auth')

    if request.method != 'POST':
        return redirect('home')

    product = Product.objects.filter(pk=product_id).first()
    if not product:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Product not found.'}, status=404)
        return redirect('home')

    cart, _ = Cart.objects.get_or_create(user=request.user)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        item.quantity += 1
        item.save(update_fields=['quantity'])

    # get updated cart count
    cart_count = CartItem.objects.filter(cart__user=request.user).aggregate(
        total=Sum('quantity'))['total'] or 0

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'ok',
            'message': f'Added {product.name} to cart.',
            'cart_count': cart_count,
        })

    messages.success(request, f'Added {product.name} to cart.')
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required(login_url='auth')
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = CartItem.objects.filter(cart=cart).select_related('product')
    items = []
    total = 0

    for item in cart_items:
        line_total = item.product.price * item.quantity
        total += line_total
        items.append({
            'product': item.product,
            'quantity': item.quantity,
            'line_total': line_total,
        })

    return render(request, 'cart.html', {
        'items': items,
        'total': total,
        'cart_count': _cart_count(request),
    })


@login_required(login_url='auth')
def update_cart_item(request, product_id):
    if request.method != 'POST':
        return redirect('cart')

    cart, _ = Cart.objects.get_or_create(user=request.user)
    item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
    if not item:
        messages.error(request, 'Cart item not found.')
        return redirect('cart')

    try:
        quantity = int(request.POST.get('quantity', item.quantity))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid quantity value.')
        return redirect('cart')

    if quantity <= 0:
        item.delete()
        messages.success(request, 'Item removed from cart.')
    else:
        item.quantity = quantity
        item.save(update_fields=['quantity'])
        messages.success(request, 'Cart updated.')

    return redirect('cart')


@login_required(login_url='auth')
def remove_cart_item(request, product_id):
    if request.method != 'POST':
        return redirect('cart')

    cart, _ = Cart.objects.get_or_create(user=request.user)
    deleted, _ = CartItem.objects.filter(cart=cart, product_id=product_id).delete()
    if deleted:
        messages.success(request, 'Item removed from cart.')
    else:
        messages.error(request, 'Cart item not found.')

    return redirect('cart')


def auth_page(request):
    return render(request, 'auth.html')


# ----------------------
# REGISTER
# ----------------------

def register_user(request):
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect('auth')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect('auth')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
            return redirect('auth')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        # Auto login after registration
        login(request, user)

        messages.success(request, "Account created successfully")
        return redirect('home')

    return redirect('auth')


# ----------------------
# LOGIN
# ----------------------

def login_user(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('home')  # Redirect to homepage
        else:
            messages.error(request, "Invalid username or password")
            return redirect('auth')

    return redirect('auth')


# ----------------------
# USER DASHBOARD (Optional)
# ----------------------

@login_required(login_url='auth')
def dashboard(request):
    return render(request, 'dashboard.html')  # Create dashboard.html

@login_required(login_url='auth')
def toggle_favourite(request, product_id):
    if request.method == 'POST':
        product = Product.objects.filter(pk=product_id).select_related('category').first()
        if product:
            fav, created = Favorite.objects.get_or_create(
                user=request.user, product=product
            )
            if not created:
                fav.delete()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'ok',
                    'product': {
                        'id':          str(product.id),
                        'name':        product.name,
                        'category':    product.category.name,
                        'description': product.description,
                        'price':       str(product.price),
                        'image':       product.image.url,
                        'in_stock':    product.in_stock,
                    }
                })

    return redirect(request.META.get('HTTP_REFERER', 'home'))


# ----------------------
# LOGOUT
# ----------------------

def logout_user(request):
    logout(request)
    messages.success(request, "Logged out successfully")
    return redirect('home')


from django.http import JsonResponse

def products_json(request):
    products = Product.objects.select_related('category').all()

    # 🔍 SEARCH
    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    # 🏷 CATEGORY
    category = request.GET.get('category', 'all') or 'all'
    if category == 'featured':
        products = products.filter(is_featured=True)
    elif category == 'new':
        products = products.filter(is_new=True)
    elif category == 'out-of-stock':
        products = products.filter(in_stock=False)
    elif category != 'all':
        products = products.filter(category__slug=category)

    # 🔄 SORT
    sort = request.GET.get('sort', '') or ''
    sort_map = {
        'name-asc':   'name',
        'name-desc':  '-name',
        'price-low':  'price',
        'price-high': '-price',
    }
    if sort in sort_map:
        products = products.order_by(sort_map[sort])

    data = []
    for p in products:
        data.append({
            'id':          str(p.id),
            'name':        p.name,
            'category':    p.category.name,
            'description': p.description,
            'price':       str(p.price),
            'image':       p.image.url,
            'in_stock':    p.in_stock,
            'is_new':      p.is_new,
            'is_featured': p.is_featured,
        })

    return JsonResponse({'products': data})

# ----------------------
# SUPERUSER - TRANSACTIONS
# ----------------------

@superuser_required
def transactions_list(request):
    """Display all transactions (Superuser only)"""
    # Get all transactions ordered by date
    transactions = Transaction.objects.select_related('user', 'order').all()
    
    # Filter by status if provided
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all' and status_filter:
        transactions = transactions.filter(status=status_filter)
    
    # Filter by transaction type if provided
    type_filter = request.GET.get('type', 'all')
    if type_filter != 'all' and type_filter:
        transactions = transactions.filter(transaction_type=type_filter)
    
    # Search by username or order ID
    search_query = request.GET.get('search', '').strip()
    if search_query:
        transactions = transactions.filter(
            Q(user__username__icontains=search_query) |
            Q(order__id__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(transactions, 20)  # Show 20 transactions per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'transactions': page_obj.object_list,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search_query': search_query,
        'status_choices': Transaction._meta.get_field('status').choices,
        'type_choices': Transaction._meta.get_field('transaction_type').choices,
    }
    
    return render(request, 'transactions_list.html', context)


@superuser_required
def transaction_detail(request, transaction_id):
    """View detailed transaction information"""
    transaction = Transaction.objects.select_related('user', 'order').get(id=transaction_id)
    
    context = {
        'transaction': transaction,
    }
    
    return render(request, 'transaction_detail.html', context)


@superuser_required
def transaction_stats(request):
    """Display transaction statistics and analytics"""
    from django.db.models import Sum, Count
    from datetime import timedelta
    from django.utils import timezone
    
    # Total statistics
    total_transactions = Transaction.objects.count()
    total_revenue = Transaction.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    completed_transactions = Transaction.objects.filter(status='completed').count()
    failed_transactions = Transaction.objects.filter(status='failed').count()
    pending_transactions = Transaction.objects.filter(status='pending').count()
    
    # Last 30 days statistics
    last_30_days = timezone.now() - timedelta(days=30)
    recent_transactions = Transaction.objects.filter(created_at__gte=last_30_days)
    recent_revenue = recent_transactions.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    recent_count = recent_transactions.count()
    
    # Transactions by type
    by_type = Transaction.objects.values('transaction_type').annotate(count=Count('id'), total=Sum('amount'))
    
    # Transactions by status
    by_status = Transaction.objects.values('status').annotate(count=Count('id'), total=Sum('amount'))
    
    context = {
        'total_transactions': total_transactions,
        'total_revenue': total_revenue,
        'completed_transactions': completed_transactions,
        'failed_transactions': failed_transactions,
        'pending_transactions': pending_transactions,
        'recent_revenue': recent_revenue,
        'recent_count': recent_count,
        'by_type': by_type,
        'by_status': by_status,
    }
    
    return render(request, 'transaction_stats.html', context)


