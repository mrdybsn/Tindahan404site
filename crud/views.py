from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse
from django.contrib.auth.models import User, Group, Permission
from django.db.models import Sum, Count, F, Q, Prefetch, Case, When, Value, CharField, IntegerField
from django.db.models.functions import TruncDate
from datetime import datetime, timedelta
import json
import csv
from django.utils import timezone
from .models import (User, Category, Product, Sale, SaleItem, Purchase, PurchaseItem, Supplier, SystemSettings, StockAdjustment, DailyOrderCounter)
from django.contrib.auth.hashers import make_password
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db import IntegrityError

# Create your views here.

def landing_page(request):
    return render(request, 'layout/landing_page.html')

#--Login/Logout--#

def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        try:
            user = User.objects.get(username=username)

            # Check if user is admin
            if not user.role == 'admin':
                messages.error(request, 'This page is for administrators only. Please use the regular login page.')
                return redirect('crud:user_login')

            # Authenticate user
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                request.session.set_expiry(0)
                next_url = request.GET.get('next') or reverse('crud:admin_dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid password.')
        except User.DoesNotExist:
            messages.error(request, 'Username not found.')

    return render(request, 'admin_panel/auth/admin_login.html')

def user_login(request):
    error = None
    error_type = None
    
    if request.user.is_authenticated:
        if request.user.role == 'inventory_manager':
            return redirect('crud:inventory_dashboard')
        elif request.user.role == 'cashier':
            return redirect('crud:pos_dashboard')
        elif request.user.role == 'admin':
            return redirect('crud:admin_dashboard')
    
    next_url = request.GET.get('next', '')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(username=username)
            
            if user.role == 'admin':
                messages.info(request, 'Administrators must use the admin login page.')
                return redirect('crud:admin_login')
            
            if not user.check_password(password):
                error = 'Password does not match'
                error_type = 'password'
            else:
                if user.role in ['inventory_manager', 'cashier']:
                    login(request, user)
                    request.session.set_expiry(86400)
                    
                    if next_url and next_url.startswith('/'):
                        return redirect(next_url)
                    
                    if user.role == 'inventory_manager':
                        return redirect('crud:inventory_dashboard')
                    elif user.role == 'cashier':
                        return redirect('crud:pos_dashboard')
                else:
                    error = 'You do not have access to this system.'
                    error_type = 'role'
        except User.DoesNotExist:
            error = 'Username does not exist'
            error_type = 'username'
    
    context = {
        'error': error,
        'error_type': error_type,
        'next': next_url
    }
    return render(request, 'layout/user_login.html', context)

def user_logout(request):
    was_staff = request.user.is_staff if request.user.is_authenticated else False
    
    request.session.flush()
    
    logout(request)
    
    messages.success(request, 'You have been successfully logged out.')
    
    if was_staff:
        return redirect('crud:admin_login')
    else:
        return redirect('crud:user_login')
    
#--Admin Dashboard--#

def admin_dashboard(request):
    if not request.user.role == 'admin':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')

    today = timezone.now()
    last_month = today - timezone.timedelta(days=30)
    two_months_ago = last_month - timezone.timedelta(days=30)

    current_month_sales = Sale.objects.filter(transaction_date__gte=last_month).aggregate(
        total=Sum('total_amount'))['total'] or 0
    previous_month_sales = Sale.objects.filter(
        transaction_date__gte=two_months_ago,
        transaction_date__lt=last_month
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    sales_change = ((current_month_sales - previous_month_sales) / previous_month_sales * 100) if previous_month_sales > 0 else 0

    # Calculate transaction metrics
    current_month_transactions = Sale.objects.filter(transaction_date__gte=last_month).count()
    previous_month_transactions = Sale.objects.filter(
        transaction_date__gte=two_months_ago,
        transaction_date__lt=last_month
    ).count()

    transaction_change = ((current_month_transactions - previous_month_transactions) / previous_month_transactions * 100) if previous_month_transactions > 0 else 0

    # Get product metrics
    total_products = Product.objects.count()
    out_of_stock = Product.objects.filter(stock_quantity=0).count()
    low_stock = Product.objects.filter(stock_quantity__gt=0, stock_quantity__lte=10).count()

    # Get user metrics
    total_users = User.objects.count()
    active_users = User.objects.filter(last_login__date=today.date()).count()

    # Get sales data for chart
    sales_data = []
    sales_labels = []
    
    # Get the start of today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get sales for the last 7 days
    for i in range(6, -1, -1):  # Count down from 6 to 0
        date_start = today_start - timezone.timedelta(days=i)
        date_end = date_start + timezone.timedelta(days=1)
        
        daily_sales = Sale.objects.filter(
            transaction_date__gte=date_start,
            transaction_date__lt=date_end
        ).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')

        sales_data.append(float(daily_sales))
        sales_labels.append(date_start.strftime('%b %d'))

    # Get top selling products for the last 30 days
    last_30_days = today_start - timezone.timedelta(days=30)
    top_products = SaleItem.objects.filter(
        sale__transaction_date__gte=last_30_days
    ).values(
        'product__product_name'
    ).annotate(
        total_sold=Sum('quantity')
    ).filter(
        product__product_name__isnull=False  # Exclude products that might have been deleted
    ).order_by('-total_sold')[:5]

    # If no products have been sold, get the 5 most recent products
    if not top_products:
        top_products = Product.objects.filter(
            is_active=True
    ).values(
            'product_name'
    ).annotate(
            total_sold=Value(0, output_field=IntegerField())
        ).order_by('-created_at')[:5]

    product_labels = [p['product__product_name'] if 'product__product_name' in p else p['product_name'] for p in top_products]
    product_data = [float(p['total_sold']) for p in top_products]

    # Ensure we have at least one product for the chart
    if not product_labels:
        product_labels = ['No Products']
        product_data = [0]

    # Get recent activities
    recent_activities = []

    # Add recent sales
    recent_sales = Sale.objects.select_related('cashier').order_by('-transaction_date')[:5]
    for sale in recent_sales:
        recent_activities.append({
            'icon': 'shopping_cart',
            'description': f'New sale of ₱{sale.total_amount:.2f}',
            'timestamp': sale.transaction_date
        })

    # Add recent stock adjustments
    recent_adjustments = StockAdjustment.objects.select_related('product').order_by('-date')[:5]
    for adjustment in recent_adjustments:
        recent_activities.append({
            'icon': 'inventory',
            'description': f'Stock adjusted for {adjustment.product.product_name}',
            'timestamp': adjustment.date
        })

    # Sort activities by timestamp
    recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_activities = recent_activities[:5]

    context = {
        'total_sales': current_month_sales,
        'sales_change': sales_change,
        'total_transactions': current_month_transactions,
        'transaction_change': transaction_change,
        'total_products': total_products,
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'total_users': total_users,
        'active_users': active_users,
        'sales_labels': json.dumps(sales_labels, default=str),
        'sales_data': json.dumps([float(x) for x in sales_data], default=str),
        'product_labels': json.dumps(product_labels, default=str),
        'product_data': json.dumps([float(x) for x in product_data], default=str),
        'recent_activities': recent_activities
    }

    return render(request, 'admin_panel/dashboard/admin_dashboard.html', context)

def admin_dashboard_data(request):
    if not request.user.role == 'admin':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Get date ranges
    today = timezone.now()
    last_month = today - timezone.timedelta(days=30)
    two_months_ago = last_month - timezone.timedelta(days=30)

    # Calculate sales metrics
    current_month_sales = Sale.objects.filter(transaction_date__gte=last_month).aggregate(
        total=Sum('total_amount'))['total'] or 0
    previous_month_sales = Sale.objects.filter(
        transaction_date__gte=two_months_ago,
        transaction_date__lt=last_month
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    sales_change = ((current_month_sales - previous_month_sales) / previous_month_sales * 100) if previous_month_sales > 0 else 0

    # Calculate transaction metrics
    current_month_transactions = Sale.objects.filter(transaction_date__gte=last_month).count()
    previous_month_transactions = Sale.objects.filter(
        transaction_date__gte=two_months_ago,
        transaction_date__lt=last_month
    ).count()

    transaction_change = ((current_month_transactions - previous_month_transactions) / previous_month_transactions * 100) if previous_month_transactions > 0 else 0

    # Get product metrics
    total_products = Product.objects.count()
    out_of_stock = Product.objects.filter(stock_quantity=0).count()
    low_stock = Product.objects.filter(stock_quantity__gt=0, stock_quantity__lte=10).count()

    # Get user metrics
    total_users = User.objects.count()
    active_users = User.objects.filter(last_login__date=today.date()).count()

    # Get sales data for chart
    sales_data = []
    sales_labels = []
    for i in range(7):
        date = today - timezone.timedelta(days=i)
        daily_sales = Sale.objects.filter(
            transaction_date__date=date.date()
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        sales_data.insert(0, float(daily_sales))
        sales_labels.insert(0, date.strftime('%b %d'))

    # Get top selling products
    top_products = SaleItem.objects.values(
        'product__product_name'
    ).annotate(
        total_sold=Sum('quantity')
    ).order_by('-total_sold')[:5]

    product_labels = [p['product__product_name'] for p in top_products]
    product_data = [float(p['total_sold']) for p in top_products]

    # Get recent activities
    recent_activities = []

    # Add recent sales
    recent_sales = Sale.objects.select_related('cashier').order_by('-transaction_date')[:5]
    for sale in recent_sales:
        recent_activities.append({
            'icon': 'shopping_cart',
            'description': f'New sale of ₱{sale.total_amount:.2f} by {sale.cashier.get_full_name()}',
            'timestamp': sale.transaction_date.strftime('%Y-%m-%d %H:%M:%S')
        })

    # Add recent stock adjustments
    recent_adjustments = StockAdjustment.objects.select_related('product').order_by('-date')[:5]
    for adjustment in recent_adjustments:
        recent_activities.append({
            'icon': 'inventory',
            'description': f'Stock adjusted for {adjustment.product.product_name} ({adjustment.quantity_change:+d})',
            'timestamp': adjustment.date.strftime('%Y-%m-%d %H:%M:%S')
        })

    # Add recent user logins
    recent_logins = User.objects.filter(
        last_login__isnull=False
    ).order_by('-last_login')[:5]
    for user in recent_logins:
        recent_activities.append({
            'icon': 'person',
            'description': f'{user.get_full_name()} logged in',
            'timestamp': user.last_login.strftime('%Y-%m-%d %H:%M:%S')
        })

    # Sort activities by timestamp and limit to 5
    recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_activities = recent_activities[:5]

    return JsonResponse({
        'total_sales': float(current_month_sales),
        'sales_change': float(sales_change),
        'total_transactions': current_month_transactions,
        'transaction_change': float(transaction_change),
        'total_products': total_products,
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'total_users': total_users,
        'active_users': active_users,
        'sales_labels': sales_labels,
        'sales_data': sales_data,
        'product_labels': product_labels,
        'product_data': product_data,
        'recent_activities': recent_activities
    })

#--User Management--#

def admin_users(request):
    users = User.objects.all()
    return render(request, 'admin_panel/users/admin_users.html', {'users': users})

def add_user(request):
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            password = request.POST.get('password')
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            email = request.POST.get('email')
            contact_number = request.POST.get('contact_number')
            gender = request.POST.get('gender')
            birth_date = request.POST.get('birth_date') or None
            role = request.POST.get('role')
            address = request.POST.get('address')
            is_active = request.POST.get('is_active') == 'on'

            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                email=email,
                contact_number=contact_number,
                gender=gender,
                birth_date=birth_date,
                role=role,
                address=address,
                is_active=is_active
            )

            messages.success(request, f'User {username} was created successfully.')

            if '_addanother' in request.POST:
                return redirect('crud:add_user')
            return redirect('crud:admin_users')

        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
            return render(request, 'admin_panel/users/add_user.html')

    return render(request, 'admin_panel/users/add_user.html')

def edit_user(request, user_id):
    from .models import User
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('crud:admin_users')

    if request.method == 'POST':
        try:
            # Get form data
            user.username = request.POST.get('username')
            if request.POST.get('password'):  # Only update password if provided
                user.set_password(request.POST.get('password'))
            user.first_name = request.POST.get('first_name')
            user.last_name = request.POST.get('last_name')
            user.email = request.POST.get('email')
            user.contact_number = request.POST.get('contact_number')
            user.gender = request.POST.get('gender')
            user.birth_date = request.POST.get('birth_date') or None
            user.role = request.POST.get('role')
            user.address = request.POST.get('address')
            user.is_active = request.POST.get('is_active') == 'on'

            user.save()
            messages.success(request, f'User {user.username} was updated successfully.')
            return redirect('crud:admin_users')

        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
            return render(request, 'admin_panel/users/edit_user.html', {'user': user})

    return render(request, 'admin_panel/users/edit_user.html', {'user': user})

def delete_user(request, user_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('crud:admin_users')
        
    try:
        user = User.objects.get(pk=user_id)
        username = user.username
        user.delete()
        messages.success(request, f'User {username} was deleted successfully.')
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
    except Exception as e:
        messages.error(request, f'Error deleting user: {str(e)}')
    return redirect('crud:admin_users')

#--Product Management--#

def admin_products(request):
    products_list = Product.objects.select_related('category').all().order_by('product_name')
    paginator = Paginator(products_list, 10) 
    page_number = request.GET.get('page')
    products = paginator.get_page(page_number)
    
    context = {
        'products': products
    }
    return render(request, 'admin_panel/products/admin_products.html', context)

def add_product(request):
    if request.method == 'POST':
        product_name = request.POST.get('product_name')
        category_id = request.POST.get('category')
        product_description = request.POST.get('product_description')
        sku = request.POST.get('sku')
        barcode = request.POST.get('barcode')
        stock_quantity = request.POST.get('stock_quantity')
        minimum_stock_level = request.POST.get('minimum_stock_level')
        price = request.POST.get('price')
        cost_price = request.POST.get('cost_price')
        product_image = request.FILES.get('product_image')

        try:
            category = Category.objects.get(id=category_id)
            
            Product.objects.create(
                product_name=product_name,
                category=category,
                product_description=product_description,
                sku=sku,
                barcode=barcode,
                stock_quantity=stock_quantity,
                minimum_stock_level=minimum_stock_level,
                price=price,
                cost_price=cost_price,
                image=product_image
            )
            messages.success(request, 'Product added successfully!')
            return redirect('crud:admin_products')
        except Category.DoesNotExist:
            messages.error(request, 'Selected category does not exist.')
        except Exception as e:
            messages.error(request, f'Error adding product: {e}')
            
    categories = Category.objects.all()
    context = {'categories': categories}
    return render(request, 'admin_panel/products/add_product.html', context)

def edit_product(request, product_id):
    try:
        product = get_object_or_404(Product, product_id=product_id)
        categories = Category.objects.all()
        if request.method == 'POST':
            try:
                product.product_name = request.POST.get('product_name')
                product.product_description = request.POST.get('product_description')
                product.category_id = request.POST.get('category')
                product.price = request.POST.get('price')
                product.cost_price = request.POST.get('cost_price')
                product.stock_quantity = request.POST.get('stock_quantity')
                product.sku = request.POST.get('sku')
                product.barcode = request.POST.get('barcode')
                product.minimum_stock_level = request.POST.get('minimum_stock_level')

                if request.FILES.get('product_image'):
                    if product.image:
                        product.image.delete(save=False)
                    product.image = request.FILES['product_image']

                product.save()
                messages.success(request, f'Product {product.product_name} was updated successfully.')
                return redirect('crud:admin_products')

            except Exception as e:
                messages.error(request, f'Error updating product: {str(e)}')

        return render(request, 'admin_panel/products/edit_product.html', {
            'product': product,
            'categories': categories
        })

    except Product.DoesNotExist:
        messages.error(request, 'Product not found.')
        return redirect('crud:admin_products')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
        return redirect('crud:admin_products')
    
def delete_product(request, product_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('crud:admin_products')
    
    try:
        product = Product.objects.get(pk=product_id)
        product_name = product.product_name
        product.delete()
        messages.success(request, f'Product "{product_name}" was deleted successfully.')
    except Product.DoesNotExist:
        messages.error(request, 'Product not found.')
    except Exception as e:
        messages.error(request, f'Error deleting product: {str(e)}')

    return redirect('crud:admin_products')

def confirm_delete_product(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    return render(request, 'admin_panel/products/delete_product.html', {'product': product})

#--Categories Management--#

def admin_categories(request):
    categories = Category.objects.all()
    return render(request, 'admin_panel/categories/admin_categories.html', {'categories': categories})

def add_category(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method == 'POST':
        try:
            category_name = request.POST.get('category_name')
            category_description = request.POST.get('description')
            if not category_name:
                messages.error(request, 'Category name is required.')
                return redirect('crud:category_list')
                
            category = Category.objects.create(
                category_name=category_name,
                category_description=category_description
            )
            messages.success(request, f'Category "{category_name}" was created successfully.')
            return redirect('crud:category_list')
        except IntegrityError:
            messages.error(request, 'A category with this name already exists.')
        except Exception as e:
            messages.error(request, f'Error creating category: {str(e)}')

    return redirect('crud:category_list')

def edit_category(request, category_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    try:
        category = Category.objects.get(pk=category_id)
    except Category.DoesNotExist:
        messages.error(request, 'Category not found.')
        return redirect('crud:category_list')

    if request.method == 'POST':
        try:
            category_name = request.POST.get('category_name')
            category_description = request.POST.get('description')
            if not category_name:
                messages.error(request, 'Category name is required.')
                return redirect('crud:category_list')
                
            category.category_name = category_name
            category.category_description = category_description
            category.save()
            messages.success(request, f'Category "{category_name}" was updated successfully.')
            return redirect('crud:category_list')
        except IntegrityError:
            messages.error(request, 'A category with this name already exists.')
        except Exception as e:
            messages.error(request, f'Error updating category: {str(e)}')

    return redirect('crud:category_list')

def confirm_delete_category(request, category_id):
    category = get_object_or_404(Category, pk=category_id)
    return render(request, 'admin_panel/categories/delete_category.html', {'category': category})

def delete_category(request, category_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('crud:admin_categories')

    try:
        category = Category.objects.get(pk=category_id)
        category_name = category.category_name
        category.delete()
        messages.success(request, f'Category "{category_name}" was deleted successfully.')
    except Category.DoesNotExist:
        messages.error(request, 'Category not found.')
    except Exception as e:
        messages.error(request, f'Error deleting category: {str(e)}')

    return redirect('crud:admin_categories')


#--Sales Management--#
def admin_sales(request):
    sales = Sale.objects.all()
    return render(request, 'admin_panel/sales/admin_sales.html', {'sales': sales})

def add_sale(request):
    from .models import User
    if request.method == 'POST':
        try:
            total_amount = request.POST.get('total_amount')
            cashier_id = request.POST.get('cashier')
            payment_method = request.POST.get('payment_method')
            customer_name = request.POST.get('customer_name')

            sale = Sale.objects.create(
                total_amount=total_amount,
                cashier_id=cashier_id,
                payment_method=payment_method,
                customer_name=customer_name
            )

            messages.success(request, f'Sale #{sale.id} was created successfully.')

            if '_addanother' in request.POST:
                return redirect('crud:add_sale')
            return redirect('crud:admin_sales')

        except Exception as e:
            messages.error(request, f'Error creating sale: {str(e)}')
            return render(request, 'admin_panel/sales/add_sale.html', {'users': User.objects.filter(role='cashier')})

    return render(request, 'admin_panel/sales/add_sale.html', {'users': User.objects.filter(role='cashier')})

def edit_sale(request, sale_id):
    from .models import User
    try:
        sale = Sale.objects.get(pk=sale_id)
    except Sale.DoesNotExist:
        messages.error(request, 'Sale not found.')
        return redirect('crud:admin_sales')

    if request.method == 'POST':
        try:
            # Get form data
            sale.total_amount = request.POST.get('total_amount')
            sale.cashier_id = request.POST.get('cashier')
            sale.payment_method = request.POST.get('payment_method')
            sale.customer_name = request.POST.get('customer_name')

            sale.save()
            messages.success(request, f'Sale #{sale.id} was updated successfully.')
            return redirect('crud:admin_sales')

        except Exception as e:
            messages.error(request, f'Error updating sale: {str(e)}')

    return render(request, 'admin/sales/edit_sale.html', {
        'sale': sale,
        'users': User.objects.filter(role='cashier')
    })

def delete_sale(request, sale_id):
    try:
        sale = Sale.objects.get(pk=sale_id)
        sale_id = sale.id
        sale.delete()
        messages.success(request, f'Sale #{sale_id} was deleted successfully.')
    except Sale.DoesNotExist:
        messages.error(request, 'Sale not found.')
    except Exception as e:
        messages.error(request, f'Error deleting sale: {str(e)}')
    return redirect('crud:admin_sales')

#--Sales Items--#
def admin_sales_items(request):
    sale_items = SaleItem.objects.all()
    return render(request, 'admin_panel/sale_items/admin_sales_items.html', {'sale_items': sale_items})

def add_sales_item(request, sale_id):
    from .models import Sale, Product
    try:
        sale = get_object_or_404(Sale, id=sale_id)
    except Sale.DoesNotExist:
        messages.error(request, 'Sale not found.')
        return redirect('crud:admin_sales')

    if request.method == 'POST':
        try:
            # Get form data
            product_id = request.POST.get('product')
            quantity = request.POST.get('quantity')
            unit_price = request.POST.get('unit_price')

            # Create sale item
            sale_item = SaleItem.objects.create(
                sale=sale,
                product_id=product_id,
                quantity=quantity,
                unit_price_at_sale=unit_price,
                subtotal=float(quantity) * float(unit_price)
            )

            messages.success(request, 'Sale item was created successfully.')
            return redirect('crud:edit_sale', sale_id=sale_id)

        except Exception as e:
            messages.error(request, f'Error creating sale item: {str(e)}')
            return render(request, 'admin/sale_items/add_sale_item.html', {
                'sale': sale,
                'products': Product.objects.filter(is_active=True)
            })

    return render(request, 'admin/sale_items/add_sale_item.html', {
        'sale': sale,
        'products': Product.objects.filter(is_active=True)
    })

def edit_sales_item(request, sale_item_id):
    from .models import Sale, Product
    try:
        sale_item = SaleItem.objects.get(pk=sale_item_id)
    except SaleItem.DoesNotExist:
        messages.error(request, 'Sale item not found.')
        return redirect('crud:admin_sale_items')

    if request.method == 'POST':
        try:
            # Get form data
            sale_item.sale_id = request.POST.get('sale')
            sale_item.product_id = request.POST.get('product')
            sale_item.quantity = request.POST.get('quantity')
            sale_item.unit_price_at_sale = request.POST.get('unit_price')
            sale_item.subtotal = float(sale_item.quantity) * float(sale_item.unit_price_at_sale)

            sale_item.save()
            messages.success(request, 'Sale item was updated successfully.')
            return redirect('crud:admin_sale_items')

        except Exception as e:
            messages.error(request, f'Error updating sale item: {str(e)}')

    return render(request, 'admin/sale_items/edit_sale_item.html', {
        'sale_item': sale_item,
        'sales': Sale.objects.all(),
        'products': Product.objects.filter(is_active=True)
    })

def delete_sales_item(request, sale_item_id):
    try:
        sale_item = SaleItem.objects.get(pk=sale_item_id)
        sale_item.delete()
        messages.success(request, 'Sale item was deleted successfully.')
    except SaleItem.DoesNotExist:
        messages.error(request, 'Sale item not found.')
    except Exception as e:
        messages.error(request, f'Error deleting sale item: {str(e)}')
    return redirect('crud:admin_sale_items')

#--Purchase Orders--#
def admin_purchase_orders(request): 
    purchase_orders = Purchase.objects.all().order_by('-purchase_date')
    paginator = Paginator(purchase_orders, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'purchase_orders': page_obj,
        'suppliers': Supplier.objects.all(),
        'products': Product.objects.all(),
    }
    return render(request, 'admin_panel/purchase_orders/admin_purchase_orders.html', context)

def admin_add_purchase_order(request):
    from .models import Supplier, User
    if request.method == 'POST':
        try:
            supplier_id = request.POST.get('supplier')
            total_cost = request.POST.get('total_cost')
            received_by_id = request.POST.get('received_by')
            status = request.POST.get('status')

            purchase = Purchase.objects.create(
                supplier_id=supplier_id,
                total_cost=total_cost,
                received_by_id=received_by_id,
                status=status
            )

            messages.success(request, f'Purchase order #{purchase.id} was created successfully.')

            if '_addanother' in request.POST:
                return redirect('crud:admin_add_purchase_order')
            return redirect('crud:admin_purchase_orders')

        except Exception as e:
            messages.error(request, f'Error creating purchase order: {str(e)}')
            return render(request, 'admin_panel/purchase_orders/add_purchase_order.html', {
                'suppliers': Supplier.objects.all(),
                'users': User.objects.all()
            })

    return render(request, 'admin_panel/purchase_orders/add_purchase_order.html', {
        'suppliers': Supplier.objects.all(),
        'users': User.objects.all()
    })

def edit_purchase_orders(request, purchase_id):
    from .models import Supplier, User
    try:
        purchase = Purchase.objects.get(pk=purchase_id)
    except Purchase.DoesNotExist:
        messages.error(request, 'Purchase order not found.')
        return redirect('crud:admin_purchase_orders')

    if request.method == 'POST':
        try:
            purchase.supplier_id = request.POST.get('supplier')
            purchase.total_cost = request.POST.get('total_cost')
            purchase.received_by_id = request.POST.get('received_by')
            purchase.status = request.POST.get('status')

            purchase.save()
            messages.success(request, f'Purchase order #{purchase.id} was updated successfully.')
            return redirect('crud:admin_purchase_orders')

        except Exception as e:
            messages.error(request, f'Error updating purchase order: {str(e)}')

    return render(request, 'admin_panel/purchase_orders/edit_purchase_orders.html', {
        'purchase': purchase,
        'suppliers': Supplier.objects.all(),
        'users': User.objects.all()
    })

def cancel_purchase_order(request, pk):
    purchase_order = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        purchase_order.status = 'cancelled'
        purchase_order.save()
        messages.info(request, f"Purchase Order #{pk} has been cancelled.")
        return redirect('crud:admin_purchase_orders')
    
    context = {
        'purchase_order': purchase_order
    }
    return render(request, 'admin_panel/purchase_orders/cancel_purchase_orders.html', context)

#--Purchase Items--#
def admin_purchase_items(request):
    purchase_items = PurchaseItem.objects.all()
    return render(request, 'admin_panel/purchase_items/admin_purchase_items.html', {'purchase_items': purchase_items})

def add_purchase_item(request):
    from .models import Purchase, Product
    if request.method == 'POST':
        try:
            purchase_id = request.POST.get('purchase')
            product_id = request.POST.get('product')
            quantity = request.POST.get('quantity')
            unit_cost = request.POST.get('unit_cost')
            received_quantity = request.POST.get('received_quantity')

            purchase_item = PurchaseItem.objects.create(
                purchase_id=purchase_id,
                product_id=product_id,
                quantity=quantity,
                unit_cost_at_purchase=unit_cost,
                subtotal_cost=float(quantity) * float(unit_cost),
                received_quantity=received_quantity
            )

            messages.success(request, 'Purchase item was created successfully.')

            if '_addanother' in request.POST:
                return redirect('crud:add_purchase_item')
            return redirect('crud:admin_purchase_items')

        except Exception as e:
            messages.error(request, f'Error creating purchase item: {str(e)}')
            return render(request, 'admin/purchase_items/add_purchase_item.html', {
                'purchases': Purchase.objects.all(),
                'products': Product.objects.filter(is_active=True)
            })

    return render(request, 'admin/purchase_items/add_purchase_item.html', {
        'purchases': Purchase.objects.all(),
        'products': Product.objects.filter(is_active=True)
    })

def edit_purchase_item(request, purchase_item_id):
    from .models import Purchase, Product
    try:
        purchase_item = PurchaseItem.objects.get(pk=purchase_item_id)
    except PurchaseItem.DoesNotExist:
        messages.error(request, 'Purchase item not found.')
        return redirect('crud:admin_purchase_items')

    if request.method == 'POST':
        try:
            # Get form data
            purchase_item.purchase_id = request.POST.get('purchase')
            purchase_item.product_id = request.POST.get('product')
            purchase_item.quantity = request.POST.get('quantity')
            purchase_item.unit_cost_at_purchase = request.POST.get('unit_cost')
            purchase_item.received_quantity = request.POST.get('received_quantity')
            purchase_item.subtotal_cost = float(purchase_item.quantity) * float(purchase_item.unit_cost_at_purchase)

            purchase_item.save()
            messages.success(request, 'Purchase item was updated successfully.')
            return redirect('crud:admin_purchase_items')

        except Exception as e:
            messages.error(request, f'Error updating purchase item: {str(e)}')

    return render(request, 'admin/purchase_items/edit_purchase_item.html', {
        'purchase_item': purchase_item,
        'purchases': Purchase.objects.all(),
        'products': Product.objects.filter(is_active=True)
    })

def delete_purchase_item(request, purchase_item_id):
    try:
        purchase_item = PurchaseItem.objects.get(pk=purchase_item_id)
        purchase_item.delete()
        messages.success(request, 'Purchase item was deleted successfully.')
    except PurchaseItem.DoesNotExist:
        messages.error(request, 'Purchase item not found.')
    except Exception as e:
        messages.error(request, f'Error deleting purchase item: {str(e)}')
    return redirect('crud:admin_purchase_items')

#--Suppliers Management--#
def admin_suppliers(request):
    suppliers = Supplier.objects.all()
    return render(request, 'admin_panel/suppliers/admin_suppliers.html', {'suppliers': suppliers})

def admin_add_supplier(request):
    if not request.user.role == 'admin':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method == 'POST':
        try:
            company_name = request.POST.get('company_name')
            contact_person = request.POST.get('contact_person')
            contact_number = request.POST.get('contact_number')
            email = request.POST.get('email')
            address = request.POST.get('address')

            # Create new supplier
            supplier = Supplier.objects.create(
                company_name=company_name,
                contact_person=contact_person,
                contact_number=contact_number,
                email=email,
                address=address
            )

            messages.success(request, 'Supplier added successfully.')
            return redirect('crud:admin_suppliers')
        except Exception as e:
            messages.error(request, f'Error adding supplier: {str(e)}')

    return render(request, 'admin_panel/suppliers/admin_add_supplier.html')

def add_supplier(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method == 'POST':
        try:
            company_name = request.POST.get('company_name')
            contact_person = request.POST.get('contact_person')
            contact_number = request.POST.get('contact_number')
            email = request.POST.get('email')
            address = request.POST.get('address')

            # Create new supplier
            supplier = Supplier.objects.create(
                company_name=company_name,
                contact_person=contact_person,
                contact_number=contact_number,
                email=email,
                address=address
            )

            messages.success(request, 'Supplier added successfully.')
            return redirect('crud:supplier_list')
        except Exception as e:
            messages.error(request, f'Error adding supplier: {str(e)}')

    return render(request, 'inventory_manager/supplier/add_supplier.html')

def edit_supplier(request, supplier_id):
    if not request.user.role == 'admin':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    try:
        supplier = Supplier.objects.get(id=supplier_id)
    except Supplier.DoesNotExist:
        messages.error(request, 'Supplier not found.')
        return redirect('crud:admin_suppliers')

    if request.method == 'POST':
        try:
            supplier.company_name = request.POST.get('company_name')
            supplier.contact_person = request.POST.get('contact_person')
            supplier.contact_number = request.POST.get('contact_number')
            supplier.email = request.POST.get('email')
            supplier.address = request.POST.get('address')
            supplier.save()

            messages.success(request, 'Supplier updated successfully.')
            return redirect('crud:supplier_list')
        except Exception as e:
            messages.error(request, f'Error updating supplier: {str(e)}')

    return render(request, 'admin_panel/suppliers/edit_supplier.html', {'supplier': supplier})

def delete_supplier(request, supplier_id):
    try:
        supplier = Supplier.objects.get(pk=supplier_id)
        company_name = supplier.company_name
        supplier.delete()
        messages.success(request, f'Supplier {company_name} was deleted successfully.')
    except Supplier.DoesNotExist:
        messages.error(request, 'Supplier not found.')
    except Exception as e:
        messages.error(request, f'Error deleting supplier: {str(e)}')
    return redirect('crud:admin_suppliers')

#--Reports--#
@login_required
def admin_reports(request):
    if not request.user.role == 'admin':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:admin_dashboard')
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if not start_date:
        start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    # Convert to datetime objects
    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)  # Include end date
    
    sales = Sale.objects.filter(
        transaction_date__gte=start_date,
        transaction_date__lt=end_date
    )
    
    total_revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    total_sales = sales.count()
    average_order_value = total_revenue / total_sales if total_sales > 0 else 0
    
    total_products_sold = SaleItem.objects.filter(
        sale__transaction_date__gte=start_date,
        sale__transaction_date__lt=end_date
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    daily_revenue = sales.annotate(
        date=TruncDate('transaction_date')
    ).values('date').annotate(
        revenue=Sum('total_amount')
    ).order_by('date')
    
    revenue_labels = [item['date'].strftime('%b %d') for item in daily_revenue]
    revenue_data = [float(item['revenue']) for item in daily_revenue]
    
    # Get category sales data
    category_sales = SaleItem.objects.filter(
        sale__transaction_date__gte=start_date,
        sale__transaction_date__lt=end_date
    ).values(
        'product__category__category_name'
    ).annotate(
        total_sales=Sum('quantity')
    ).order_by('-total_sales')[:5]
    
    category_labels = [item['product__category__category_name'] for item in category_sales]
    category_data = [item['total_sales'] for item in category_sales]
    
    top_products = SaleItem.objects.filter(
        sale__transaction_date__gte=start_date,
        sale__transaction_date__lt=end_date
    ).values(
        'product__product_name',
        'product__category__category_name'
    ).annotate(
        total_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price_at_sale'))
    ).order_by('-total_sold')[:10]
    
    context = {
        'start_date': start_date,
        'end_date': end_date - timedelta(days=1),  # Subtract one day to show correct end date
        'total_revenue': total_revenue,
        'total_sales': total_sales,
        'average_order_value': average_order_value,
        'total_products_sold': total_products_sold,
        'revenue_labels': revenue_labels,
        'revenue_data': revenue_data,
        'category_labels': category_labels,
        'category_data': category_data,
        'top_products': top_products,
    }
    
    return render(request, 'admin_panel/reports/admin_reports.html', context)

#--Settings--#
def admin_settings(request):
    settings = SystemSettings.get_settings()
    
    if request.method == 'POST':
        try:
            settings.company_name = request.POST.get('company_name')
            settings.company_address = request.POST.get('company_address')
            settings.company_phone = request.POST.get('company_phone')
            settings.company_email = request.POST.get('company_email')
            settings.tax_rate = Decimal(request.POST.get('tax_rate', '0.00'))
            settings.currency_symbol = request.POST.get('currency_symbol')
            settings.low_stock_threshold = int(request.POST.get('low_stock_threshold', '10'))
            settings.enable_email_notifications = request.POST.get('enable_email_notifications') == 'on'
            
            settings.save()
            messages.success(request, 'Settings updated successfully.')
            return redirect('crud:admin_settings')
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
    
    return render(request, 'admin_panel/settings/admin_settings.html', {'settings': settings})

#--Inventory--#
def admin_inventory(request):
    return render(request, 'admin/inventory/admin_inventory.html')

#--Inventory Manager--#
def supplier_list(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    suppliers = Supplier.objects.all()
    context = {
        'suppliers': suppliers,
    }
    return render(request, 'inventory_manager/supplier/supplier_list.html', context)

def purchase_orders(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    purchase_orders = Purchase.objects.select_related('supplier', 'received_by').all()
    suppliers = Supplier.objects.all()
    context = {
        'purchase_orders': purchase_orders,
        'suppliers': suppliers,
    }
    return render(request, 'inventory_manager/purchase_order/purchase_orders.html', context)

def inventory_manager_add_purchase_order(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method == 'POST':
        try:
            supplier_id = request.POST.get('supplier')
            supplier = Supplier.objects.get(id=supplier_id)
            
            purchase = Purchase.objects.create(
                supplier=supplier,
                status='pending',
                received_by=request.user
            )
            
            items = json.loads(request.POST.get('items', '[]'))
            total_cost = Decimal('0.00')
            
            for item in items:
                product = Product.objects.get(id=item['product_id'])
                quantity = Decimal(item['quantity'])
                unit_price = Decimal(item['unit_price'])
                subtotal = quantity * unit_price
                
                PurchaseItem.objects.create(
                    purchase=purchase,
                    product=product,
                    quantity=quantity,
                    unit_cost_at_purchase=unit_price,
                    subtotal_cost=subtotal
                )
                total_cost += subtotal
            
            purchase.total_cost = total_cost
            purchase.save()
            
            messages.success(request, 'Purchase order created successfully.')
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    suppliers = Supplier.objects.all()
    products = Product.objects.filter(is_active=True)
    products_data = [
        {
            'product_id': str(product.id),
            'product_name': product.product_name,
            'price': float(product.price)
        }
        for product in products
    ]
    context = {
        'suppliers': suppliers,
        'products': json.dumps(products_data)
    }
    return render(request, 'inventory_manager/purchase_order/add_purchase_order.html', context)

def edit_purchase_order(request, order_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    try:
        purchase = Purchase.objects.get(id=order_id)
        items = purchase.items.select_related('product').all()
    except Purchase.DoesNotExist:
        messages.error(request, 'Purchase order not found.')
        return redirect('crud:purchase_orders')
        
    if request.method == 'POST':
        try:
            supplier_id = request.POST.get('supplier')
            supplier = Supplier.objects.get(id=supplier_id)
            purchase.supplier = supplier
            purchase.status = request.POST.get('status')
            products = request.POST.getlist('products[]')
            quantities = request.POST.getlist('quantities[]')
            unit_prices = request.POST.getlist('unit_prices[]')
            
            total_cost = Decimal('0.00')
            
            purchase.items.all().delete()
            
            for i in range(len(products)):
                product = Product.objects.get(id=products[i])
                quantity = Decimal(quantities[i])
                unit_price = Decimal(unit_prices[i])
                subtotal = quantity * unit_price
                
                PurchaseItem.objects.create(
                    purchase=purchase,
                    product=product,
                    quantity=quantity,
                    unit_cost_at_purchase=unit_price,
                    subtotal_cost=subtotal
                )
                total_cost += subtotal
            
            purchase.total_cost = total_cost
            purchase.save()
            
            messages.success(request, 'Purchase order updated successfully.')
            return redirect('crud:view_purchase_order', order_id=purchase.id)
        except Exception as e:
            messages.error(request, f'Error updating purchase order: {str(e)}')
    
    suppliers = Supplier.objects.all()
    products = Product.objects.all()
    context = {
        'purchase': purchase,
        'suppliers': suppliers,
        'products': products,
        'items': items,
    }
    return render(request, 'inventory_manager/purchase_order/edit_purchase_order.html', context)

def delete_purchase_order(request, order_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('crud:purchase_orders')
        
    try:
        purchase = Purchase.objects.get(id=order_id)
        purchase.delete()
        messages.success(request, 'Purchase order deleted successfully.')
    except Purchase.DoesNotExist:
        messages.error(request, 'Purchase order not found.')
    except Exception as e:
        messages.error(request, f'Error deleting purchase order: {str(e)}')
    
    return redirect('crud:purchase_orders')

def stock_adjustments(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    adjustments = StockAdjustment.objects.select_related('product', 'adjusted_by').all().order_by('-date')
    products = Product.objects.all()
    
    context = {
        'adjustments': adjustments,
        'products': products,
    }
    return render(request, 'inventory_manager/stock_adjustments/stock_adjustments.html', context)

def add_stock_adjustment(request):
    if not request.user.role == 'inventory_manager':
        return JsonResponse({'error': 'Permission denied'}, status=403)
        
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
        try:
            product_id = request.POST.get('product')
            adjustment_type = request.POST.get('adjustment_type')
            quantity_change = int(request.POST.get('quantity_change'))
            reason = request.POST.get('reason')
            
            product = Product.objects.get(product_id=product_id)
            
            adjustment = StockAdjustment.objects.create(
                product=product,
                adjustment_type=adjustment_type,
                quantity_change=quantity_change,
                reason=reason,
                adjusted_by=request.user
            )
            
            product.stock_quantity += quantity_change
            if product.stock_quantity < 0:
                return JsonResponse({'error': 'Stock quantity cannot be negative'}, status=400)
            product.save()
            
            return JsonResponse({'success': True})
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

def get_stock_adjustment(request, adjustment_id):
    if not request.user.role == 'inventory_manager':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        adjustment = StockAdjustment.objects.get(id=adjustment_id)
        data = {
            'product': adjustment.product.product_id,
            'adjustment_type': adjustment.adjustment_type,
            'quantity_change': adjustment.quantity_change,
            'reason': adjustment.reason,
            'date': adjustment.date.strftime('%Y-%m-%d %H:%M:%S'),
            'adjusted_by': adjustment.adjusted_by.get_full_name()
        }
        return JsonResponse(data)
    except StockAdjustment.DoesNotExist:
        return JsonResponse({'error': 'Adjustment not found'}, status=404)

def inventory_reports(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    total_products = Product.objects.count()
    total_stock_value = Product.objects.aggregate(
        value=Sum(F('stock_quantity') * F('price'))
    )['value'] or 0
    
    products = Product.objects.annotate(
        status=Case(
            When(stock_quantity=0, then=Value('out_of_stock')),
            When(stock_quantity__lte=F('minimum_stock_level'), then=Value('low_stock')),
            default=Value('adequate'),
            output_field=CharField(),
        )
    )
    
    adequate_stock_count = products.filter(status='adequate').count()
    low_stock_count = products.filter(status='low_stock').count()
    out_of_stock_count = products.filter(status='out_of_stock').count()
    
    low_stock_products = products.filter(
        Q(status='low_stock') | Q(status='out_of_stock')
    ).select_related('category')[:10]
    
    categories = Category.objects.annotate(
        total_value=Sum(F('products__stock_quantity') * F('products__price'), default=0)
    ).order_by('-total_value')
    
    category_names = [cat.category_name for cat in categories]
    category_values = [float(cat.total_value or 0) for cat in categories]
    
    recent_movements = StockAdjustment.objects.select_related('product').order_by('-date')[:10]
    
    context = {
        'total_products': total_products,
        'total_stock_value': total_stock_value,
        'adequate_stock_count': adequate_stock_count,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'low_stock_products': low_stock_products,
        'category_names': json.dumps(category_names),
        'category_values': json.dumps(category_values),
        'recent_movements': recent_movements,
    }
    return render(request, 'inventory_manager/inventory_reports/inventory_reports.html', context)

def category_list(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    categories = Category.objects.annotate(
        product_count=Count('products'),
        total_stock=Sum('products__stock_quantity'),
        total_value=Sum(F('products__stock_quantity') * F('products__price'))
    )
    
    context = {
        'categories': categories,
    }
    return render(request, 'inventory_manager/category/category_list.html', context)

def add_category(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method == 'POST':
        try:
            category_name = request.POST.get('category_name')
            category_description = request.POST.get('description')
            if not category_name:
                messages.error(request, 'Category name is required.')
                return redirect('crud:category_list')
                
            category = Category.objects.create(
                category_name=category_name,
                category_description=category_description
            )
            messages.success(request, f'Category "{category_name}" was created successfully.')
            return redirect('crud:category_list')
        except IntegrityError:
            messages.error(request, 'A category with this name already exists.')
        except Exception as e:
            messages.error(request, f'Error creating category: {str(e)}')
    
    return redirect('crud:category_list')

def edit_category(request, category_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    try:
        category = Category.objects.get(pk=category_id)
    except Category.DoesNotExist:
        messages.error(request, 'Category not found.')
        return redirect('crud:category_list')

    if request.method == 'POST':
        try:
            category_name = request.POST.get('category_name')
            category_description = request.POST.get('description')
            if not category_name:
                messages.error(request, 'Category name is required.')
                return redirect('crud:category_list')
                
            category.category_name = category_name
            category.category_description = category_description
            category.save()
            messages.success(request, f'Category "{category_name}" was updated successfully.')
            return redirect('crud:category_list')
        except IntegrityError:
            messages.error(request, 'A category with this name already exists.')
        except Exception as e:
            messages.error(request, f'Error updating category: {str(e)}')
    
    return redirect('crud:category_list')

def delete_category(request, category_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('crud:category_list')

    try:
        category = Category.objects.get(pk=category_id)
        category_name = category.category_name
        
        # Check if category has products
        if category.products.exists():
            messages.error(request, f'Cannot delete category "{category_name}" because it has associated products.')
            return redirect('crud:category_list')
            
        category.delete()
        messages.success(request, f'Category "{category_name}" was deleted successfully.')
    except Category.DoesNotExist:
        messages.error(request, 'Category not found.')
    except Exception as e:
        messages.error(request, f'Error deleting category: {str(e)}')

    return redirect('crud:category_list')

def view_purchase_order(request, order_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    try:
        purchase = Purchase.objects.select_related('supplier').get(id=order_id)
        items = purchase.items.select_related('product').all()
        
        context = {
            'purchase': purchase,
            'items': items,
        }
        return render(request, 'inventory_manager/purchase_order/view_purchase_order.html', context)
    except Purchase.DoesNotExist:
        messages.error(request, 'Purchase order not found.')
        return redirect('crud:purchase_orders')

def cancel_purchase_order(request, order_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('crud:purchase_orders')
        
    try:
        purchase = Purchase.objects.get(id=order_id)
        if purchase.status != 'PENDING':
            messages.error(request, 'Only pending orders can be cancelled.')
            return redirect('crud:purchase_orders')
            
        purchase.status = 'CANCELLED'
        purchase.save()
        messages.success(request, 'Purchase order cancelled successfully.')
    except Purchase.DoesNotExist:
        messages.error(request, 'Purchase order not found.')
    except Exception as e:
        messages.error(request, f'Error cancelling purchase order: {str(e)}')
    
    return redirect('crud:purchase_orders')

def inventory_products(request):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    products = Product.objects.filter(is_active=True).select_related('category')
    
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(product_name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(category__category_name__icontains=search_query)
        )
    
    category_id = request.GET.get('category', '')
    if category_id:
        products = products.filter(category_id=category_id)
    
    stock_status = request.GET.get('stock_status', '')
    if stock_status == 'low':
        products = products.filter(stock_quantity__lte=F('minimum_stock_level'))
    elif stock_status == 'out':
        products = products.filter(stock_quantity=0)
    elif stock_status == 'adequate':
        products = products.filter(stock_quantity__gt=F('minimum_stock_level'))
    
    paginator = Paginator(products.order_by('product_name'), 10)
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    categories = Category.objects.all()
    
    context = {
        'products': products,
        'categories': categories,
    }
    return render(request, 'inventory_manager/product/product_list.html', context)

def inventory_add_product(request):
    if request.user.role != 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')

    categories = Category.objects.all()

    if request.method == 'POST':
        try:
            category_id = request.POST.get('category')
            product = Product.objects.create(
                product_name=request.POST.get('product_name'),
                description=request.POST.get('description'),
                sku=request.POST.get('sku'),
                price=request.POST.get('price'),
                stock_quantity=request.POST.get('stock_quantity'),
                minimum_stock_level=request.POST.get('minimum_stock_level'),
                image=request.FILES.get('image'),
                category=Category.objects.get(id=category_id) if category_id else None,
                is_active='is_active' in request.POST,
            )
            messages.success(request, 'Product added successfully.')
            return redirect('crud:inventory_products')
        except Exception as e:
            messages.error(request, f'Error adding product: {e}')

    context = {
        'categories': categories,
    }
    return render(request, 'inventory_manager/product/product_form.html', context)

def inventory_edit_product(request, product_id):
    if request.user.role != 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')

    try:
        product = Product.objects.get(product_id=product_id)
    except Product.DoesNotExist:
        messages.error(request, 'Product not found.')
        return redirect('crud:inventory_products')

    categories = Category.objects.all()

    if request.method == 'POST':
        try:
            category_id = request.POST.get('category')
            product.product_name = request.POST.get('product_name')
            product.description = request.POST.get('description')
            product.sku = request.POST.get('sku')
            product.price = request.POST.get('price')
            product.stock_quantity = request.POST.get('stock_quantity')
            product.minimum_stock_level = request.POST.get('minimum_stock_level')
            product.category = Category.objects.get(id=category_id) if category_id else None
            product.is_active = 'is_active' in request.POST
            if request.FILES.get('image'):
                product.image = request.FILES.get('image')
            product.save()
            messages.success(request, 'Product updated successfully.')
            return redirect('crud:inventory_products')
        except Exception as e:
            messages.error(request, f'Error updating product: {e}')

    context = {
        'product': product,
        'categories': categories,
    }
    return render(request, 'inventory_manager/product/product_form.html', context)

def inventory_delete_product(request, product_id):
    if not request.user.role == 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
        
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('crud:inventory_products')
        
    try:
        product = Product.objects.get(product_id=product_id)
        product.delete()
        messages.success(request, 'Product deleted successfully.')
    except Product.DoesNotExist:
        messages.error(request, 'Product not found.')
    except Exception as e:
        messages.error(request, f'Error deleting product: {str(e)}')
    
    return redirect('crud:inventory_products')     

def inventory_dashboard(request):
    if not request.user.is_authenticated:
        messages.error(request, 'Please log in to access this page.')
        return redirect('crud:user_login')
    
    if request.user.role != 'inventory_manager':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:user_login')
    
    total_products = Product.objects.count()
    total_value = Product.objects.aggregate(
        value=Sum(F('stock_quantity') * F('price'))
    )['value'] or 0
    low_stock = Product.objects.filter(stock_quantity__lte=F('minimum_stock_level')).count()
    
    top_products = Product.objects.annotate(
        sold=Sum('saleitem__quantity')
    ).order_by('-sold')[:5]
    
    stock_history = []
    
    context = {
        'total_products': total_products,
        'total_value': total_value,
        'low_stock': low_stock,
        'top_products': top_products,
        'stock_history': stock_history,
    }
    return render(request, 'inventory_manager/dashboard/inventory_dashboard.html', context)

#--POS--#

@login_required
def view_inventory(request):
    products = Product.objects.filter(is_active=True).select_related('category')
    
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(product_name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(category__category_name__icontains=search_query)
        )
    
    category_id = request.GET.get('category', '')
    if category_id:
        products = products.filter(category_id=category_id)
    
    paginator = Paginator(products.order_by('product_name'), 10)
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    categories = Category.objects.all()
    
    context = {
        'products': products,
        'categories': categories,
    }
    return render(request, 'pos/pos_inventory.html', context)

@login_required
def sales_report(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d') if date_from else datetime.now() - timedelta(days=7)
        date_to = datetime.strptime(date_to, '%Y-%m-%d') if date_to else datetime.now()
    except ValueError:
        date_from = datetime.now() - timedelta(days=7)
        date_to = datetime.now()
    
    sales = Sale.objects.filter(
        transaction_date__range=[date_from, date_to],
        cashier=request.user if request.user.role == 'cashier' else None
    ).order_by('-transaction_date')
    
    total_sales = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    total_transactions = sales.count()
    
    daily_sales = []
    daily_labels = []
    current = date_from
    while current <= date_to:
        day_sales = sales.filter(transaction_date__date=current.date()).aggregate(total=Sum('total_amount'))['total'] or 0
        daily_labels.append(current.strftime('%b %d'))
        daily_sales.append(float(day_sales))
        current += timedelta(days=1)
    
    top_products = SaleItem.objects.filter(
        sale__in=sales
    ).values(
        'product__product_name'
    ).annotate(
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:5]
    
    top_products_labels = [p['product__product_name'] for p in top_products]
    top_products_data = [p['total_quantity'] for p in top_products]
    
    context = {
        'sales': sales,
        'total_sales': total_sales,
        'total_transactions': total_transactions,
        'daily_labels': json.dumps(daily_labels),
        'daily_sales': json.dumps(daily_sales),
        'top_products_labels': json.dumps(top_products_labels),
        'top_products_data': json.dumps(top_products_data),
    }
    return render(request, 'pos/pos_sales_report.html', context)

@login_required
def export_sales(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d') if date_from else datetime.now() - timedelta(days=7)
        date_to = datetime.strptime(date_to, '%Y-%m-%d') if date_to else datetime.now()
    except ValueError:
        date_from = datetime.now() - timedelta(days=7)
        date_to = datetime.now()
    
    sales = Sale.objects.filter(
        transaction_date__range=[date_from, date_to],
        cashier=request.user if request.user.role == 'cashier' else None
    ).select_related('cashier')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="sales_report_{date_from.strftime("%Y%m%d")}_{date_to.strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Transaction ID', 'Cashier', 'Items', 'Payment Method', 'Total Amount'])
    
    for sale in sales:
        writer.writerow([
            sale.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
            sale.id,
            sale.cashier.username if sale.cashier else 'N/A',
            sale.items.count(),
            sale.get_payment_method_display(),
            sale.total_amount
        ])
    
    return response

@login_required
def get_next_order_number(request):
    try:
        counter = DailyOrderCounter.increment_counter()
        today = timezone.now().strftime('%Y%m%d')
        order_number = f"{today}-{counter:03d}"
        
        return JsonResponse({
            'order_number': order_number,
            'success': True
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'success': False
        })
    
#--POS Analytics--#
@login_required
def analytics(request):
    if not request.user.role == 'cashier':
        messages.error(request, 'Unauthorized access.')
        return redirect('crud:login')
    
    today = timezone.now()
    last_month = today - timezone.timedelta(days=30)
    
    # Get sales data
    total_sales = Sale.objects.filter(
        transaction_date__gte=last_month,
        cashier=request.user
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    transaction_count = Sale.objects.filter(
        transaction_date__gte=last_month,
        cashier=request.user
    ).count()
    
    avg_transaction = total_sales / transaction_count if transaction_count > 0 else 0
    
    # Get daily sales data for chart
    sales_dates = []
    sales_amounts = []
    current = last_month
    while current <= today:
        daily_sales = Sale.objects.filter(
            transaction_date__date=current.date(),
            cashier=request.user
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        sales_dates.append(current.strftime('%b %d'))
        sales_amounts.append(float(daily_sales))
        current += timezone.timedelta(days=1)
    
    # Get top products data
    top_products = SaleItem.objects.filter(
        sale__transaction_date__gte=last_month,
        sale__cashier=request.user
    ).values(
        'product__product_name'
    ).annotate(
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:5]
    
    top_products_labels = [p['product__product_name'] for p in top_products]
    top_products_data = [p['total_quantity'] for p in top_products]
    
    context = {
        'total_sales': total_sales,
        'transaction_count': transaction_count,
        'avg_transaction': avg_transaction,
        'sales_dates': json.dumps(sales_dates),
        'sales_amounts': json.dumps(sales_amounts),
        'top_products_labels': json.dumps(top_products_labels),
        'top_products_data': json.dumps(top_products_data),
    }
    
    return render(request, 'pos/analytics.html', context)

@login_required
def get_daily_sales(request):
    if not request.user.role == 'cashier':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else timezone.now() - timezone.timedelta(days=7)
        end_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else timezone.now()
        
        daily_sales = Sale.objects.filter(
            transaction_date__date__range=[start_date, end_date],
            cashier=request.user
        ).annotate(
            date=TruncDate('transaction_date')
        ).values('date').annotate(
            total=Sum('total_amount')
        ).order_by('date')
        
        data = {
            'labels': [sale['date'].strftime('%Y-%m-%d') for sale in daily_sales],
            'data': [float(sale['total']) for sale in daily_sales]
        }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def get_category_sales(request):
    if not request.user.role == 'cashier':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else timezone.now() - timezone.timedelta(days=7)
        end_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else timezone.now()
        
        category_sales = SaleItem.objects.filter(
            sale__transaction_date__date__range=[start_date, end_date],
            sale__cashier=request.user
        ).values(
            'product__category__category_name'
        ).annotate(
            total=Sum('quantity')
        ).order_by('-total')
        
        data = {
            'labels': [item['product__category__category_name'] for item in category_sales],
            'data': [item['total'] for item in category_sales]
        }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def get_top_products(request):
    if not request.user.role == 'cashier':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else timezone.now() - timezone.timedelta(days=7)
        end_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else timezone.now()
        
        top_products = SaleItem.objects.filter(
            sale__transaction_date__date__range=[start_date, end_date],
            sale__cashier=request.user
        ).values(
            'product__product_name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_amount=Sum(F('quantity') * F('price'))
        ).order_by('-total_quantity')[:10]
        
        data = {
            'products': list(top_products)
        }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def pos_sales_report(request):
    if not request.user.role == 'cashier':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('crud:login')
    
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d') if date_from else datetime.now() - timedelta(days=7)
        date_to = datetime.strptime(date_to, '%Y-%m-%d') if date_to else datetime.now()
    except ValueError:
        date_from = datetime.now() - timedelta(days=7)
        date_to = datetime.now()
    
    sales = Sale.objects.filter(
        transaction_date__range=[date_from, date_to],
        cashier=request.user
    ).order_by('-transaction_date')
    
    total_sales = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    total_transactions = sales.count()
    avg_transaction = total_sales / total_transactions if total_transactions > 0 else 0
    
    # Get daily sales data for chart
    daily_labels = []
    daily_sales = []
    current = date_from
    while current <= date_to:
        day_sales = sales.filter(transaction_date__date=current.date()).aggregate(total=Sum('total_amount'))['total'] or 0
        daily_labels.append(current.strftime('%b %d'))
        daily_sales.append(float(day_sales))
        current += timedelta(days=1)
    
    # Get top products data
    top_products = SaleItem.objects.filter(
        sale__in=sales
    ).values(
        'product__product_name'
    ).annotate(
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:5]
    
    top_products_labels = [p['product__product_name'] for p in top_products]
    top_products_data = [p['total_quantity'] for p in top_products]
    
    context = {
        'sales': sales,
        'total_sales': total_sales,
        'total_transactions': total_transactions,
        'avg_transaction': avg_transaction,
        'daily_labels': json.dumps(daily_labels),
        'daily_sales': json.dumps(daily_sales),
        'top_products_labels': json.dumps(top_products_labels),
        'top_products_data': json.dumps(top_products_data),
    }
    
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="sales_report_{date_from.strftime("%Y%m%d")}_{date_to.strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Transaction ID', 'Items', 'Total Amount'])
        
        for sale in sales:
            writer.writerow([
                sale.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                sale.id,
                sale.items.count(),
                sale.total_amount
            ])
        
        return response
    
    return render(request, 'pos/pos_sales_report.html', context)

@login_required
def pos_receipts(request):
    if not request.user.role == 'cashier':
        messages.error(request, 'Unauthorized access.')
        return redirect('crud:login')
    
    # Get all sales for the current cashier, ordered by date (newest first)
    sales = Sale.objects.filter(cashier=request.user).order_by('-transaction_date')
    
    # Get sale items for each sale
    sales_with_items = []
    for sale in sales:
        items = SaleItem.objects.filter(sale=sale).select_related('product')
        
        # Calculate subtotal
        subtotal = sum(item.subtotal for item in items)
        
        # Calculate discount amount
        if sale.discount_type == 'percent':
            discount_amount = subtotal * (sale.discount_value / Decimal('100'))
        else:
            discount_amount = sale.discount_value
        
        # Calculate net amount after discount
        net_amount = subtotal - discount_amount
        
        # Get amount paid and change from the sale data
        amount_paid = getattr(sale, 'amount_paid', net_amount + sale.vat_amount)  # Default to total if not stored
        change_amount = getattr(sale, 'change_amount', Decimal('0.00'))  # Default to 0 if not stored
        
        sales_with_items.append({
            'sale': sale,
            'items': items,
            'date': sale.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'amount_paid': amount_paid,
            'change_amount': change_amount
        })
    
    context = {
        'sales': sales_with_items,
        'page_title': 'POS Receipts'
    }
    
    return render(request, 'pos/pos_receipts.html', context)
    
@login_required
def pos_dashboard(request):
    if not request.user.role == 'cashier':
        messages.error(request, 'Unauthorized access.')
        return redirect('crud:login')
    
    # Get active products with their categories
    products = Product.objects.filter(is_active=True).select_related('category')
    categories = Category.objects.filter(products__is_active=True).distinct()
    
    context = {
        'products': products,
        'categories': categories,
        'page_title': 'POS Dashboard',
        'VAT_RATE': 0.12  # 12% VAT
    }
    
    return render(request, 'pos/pos_dashboard.html', context)

#--POS Product Details--#
@login_required
def get_product_details(request, product_id):
    if not request.user.role == 'cashier':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        product = Product.objects.select_related('category').get(product_id=product_id)
        
        data = {
            'success': True,
            'product': {
                'id': product.product_id,
                'name': product.product_name,
                'category': product.category.category_name,
                'price': float(product.price),
                'stock': product.stock_quantity,
                'sku': product.sku,
                'description': product.description,
                'is_active': product.is_active
            }
        }
        
        return JsonResponse(data)
    except Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Product not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def save_sale(request):
    if not request.user.role == 'cashier':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        total_amount = Decimal(str(data.get('total_amount', '0')))
        vat_amount = Decimal(str(data.get('vat_amount', '0')))
        discount_type = data.get('discount_type', '')
        discount_value = Decimal(str(data.get('discount_value', '0')))
        amount_paid = Decimal(str(data.get('amount_paid', '0')))
        
        # Validate items
        if not items:
            return JsonResponse({'error': 'No items in sale'}, status=400)
        
        # Start transaction
        with transaction.atomic():
            # First, validate all products and quantities
            products_to_update = []
            sale_items_data = []
            subtotal = Decimal('0')
            
            # Validate all products first
            for item in items:
                product = Product.objects.select_for_update().get(product_id=item['product_id'])
                quantity = int(item['quantity'])
                price = Decimal(str(item['price']))
                item_subtotal = price * quantity
                subtotal += item_subtotal
                
                # Check stock
                if product.stock_quantity < quantity:
                    raise ValidationError(f'Insufficient stock for {product.product_name}')
                
                # Store product and quantity for later update
                products_to_update.append((product, quantity))
                sale_items_data.append({
                    'product': product,
                    'quantity': quantity,
                    'unit_price_at_sale': price,
                    'subtotal': item_subtotal
                })
            
            # Calculate final amounts
            discount_amount = (subtotal * (discount_value / 100)) if discount_type == 'percent' else discount_value
            net_amount = subtotal - discount_amount
            vat_amount = net_amount * Decimal('0.12')  # 12% VAT
            total_amount = net_amount + vat_amount
            change_amount = max(amount_paid - total_amount, Decimal('0'))
            
            try:
                # First, insert the sale directly into the database
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO crud_sale 
                        (cashier_id, date, total_amount, vat_amount, discount_type, 
                         discount_value, amount_paid, change_amount)
                        VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s)
                        """, [
                            request.user.id, total_amount, vat_amount, 
                            discount_type, discount_value, amount_paid, change_amount
                        ])
                    sale_id = cursor.lastrowid
                
                # Get the created sale object
                sale = Sale.objects.get(id=sale_id)
                
                # Create sale items one by one
                for item_data in sale_items_data:
                    SaleItem.objects.create(
                        sale=sale,
                        product=item_data['product'],
                        quantity=item_data['quantity'],
                        unit_price_at_sale=item_data['unit_price_at_sale'],
                        subtotal=item_data['subtotal']
                    )
                
                # Update product stocks
                for product, quantity in products_to_update:
                    product.stock_quantity -= quantity
                    product.save()
                
                return JsonResponse({'success': True, 'sale_id': sale.id})
                
            except Exception as e:
                # If anything fails during sale creation, raise the error to trigger rollback
                raise ValidationError(f'Error creating sale: {str(e)}')
            
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
    except ValidationError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_supplier_details(request, supplier_id):
    if not request.user.role == 'inventory_manager':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        supplier = Supplier.objects.get(id=supplier_id)
        data = {
            'supplier_name': supplier.company_name,
            'contact_person': supplier.contact_person,
            'contact_number': supplier.contact_number,
            'email': supplier.email,
            'address': supplier.address,
            'is_active': supplier.is_active
        }
        return JsonResponse(data)
    except Supplier.DoesNotExist:
        return JsonResponse({'error': 'Supplier not found'}, status=404)

def deactivate_supplier(request, supplier_id):
    if not request.user.role == 'inventory_manager':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        supplier = Supplier.objects.get(id=supplier_id)
        supplier.is_active = False
        supplier.save()
        return JsonResponse({'success': True})
    except Supplier.DoesNotExist:
        return JsonResponse({'error': 'Supplier not found'}, status=404)

def activate_supplier(request, supplier_id):
    if not request.user.role == 'inventory_manager':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        supplier = Supplier.objects.get(id=supplier_id)
        supplier.is_active = True
        supplier.save()
        return JsonResponse({'success': True})
    except Supplier.DoesNotExist:
        return JsonResponse({'error': 'Supplier not found'}, status=404)

def get_category_details(request, category_id):
    if not request.user.role == 'inventory_manager':
        return JsonResponse({'error': 'Permission denied'}, status=403)
        
    try:
        category = Category.objects.get(pk=category_id)
        return JsonResponse({
            'category_name': category.category_name,
            'category_description': category.category_description or ''
        })
    except Category.DoesNotExist:
        return JsonResponse({'error': 'Category not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
