from django.urls import path
from . import views

app_name = 'crud'

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('admin/login/', views.admin_login, name='admin_login'),
    path('login/', views.user_login, name='user_login'),
    path('logout/', views.user_logout, name='user_logout'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/dashboard/data/', views.admin_dashboard_data, name='admin_dashboard_data'),
    path('admin/reports/', views.admin_reports, name='admin_reports'),

    path('admin/users/', views.admin_users, name='admin_users'),
    path('admin/users/add/', views.add_user, name='add_user'),
    path('admin/users/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('admin/users/delete/<int:user_id>/', views.delete_user, name='delete_user'),

    path('admin/categories/', views.admin_categories, name='admin_categories'),
    path('admin/categories/add/', views.add_category, name='add_category'),
    path('admin/categories/edit/<int:category_id>/', views.edit_category, name='edit_category'),
    path('admin/categories/delete/<int:category_id>/', views.confirm_delete_category, name='confirm_delete_category'),
    path('admin/categories/delete/<int:category_id>/confirm/', views.delete_category, name='delete_category'),

    path('admin/products/', views.admin_products, name='admin_products'),
    path('admin/products/add/', views.add_product, name='add_product'),
    path('admin/products/edit/<int:product_id>/', views.edit_product, name='edit_product'),
    path('admin/products/delete/<int:product_id>/', views.confirm_delete_product, name='confirm_delete_product'),
    path('admin/products/delete/<int:product_id>/confirm/', views.delete_product, name='delete_product'),

    path('admin/sales/', views.admin_sales, name='admin_sales'),
    path('admin/sales/add/', views.add_sale, name='add_sale'),
    path('admin/sales/edit/<int:sale_id>/', views.edit_sale, name='edit_sale'),
    path('admin/sales/delete/<int:sale_id>/', views.delete_sale, name='delete_sale'),

    path('admin/sales_items/', views.admin_sales_items, name='admin_sales_items'),
    path('admin/sales_items/add/<int:sale_id>/', views.add_sales_item, name='add_sales_item'),
    path('admin/sales_items/edit/<int:sale_item_id>/', views.edit_sales_item, name='edit_sales_item'),
    path('admin/sales_items/delete/<int:sale_item_id>/', views.delete_sales_item, name='delete_sales_item'),

    path('admin/purchase_orders/', views.admin_purchase_orders, name='admin_purchase_orders'),
    path('admin/purchase_orders/add/', views.admin_add_purchase_order, name='admin_add_purchase_order'),
    path('admin/purchase_orders/<int:purchase_id>/', views.view_purchase_order, name='view_purchase_order'),
    path('admin/purchase_orders/edit/<int:purchase_id>/', views.edit_purchase_orders, name='edit_purchase_orders'),
    path('admin/purchase_orders/delete/<int:purchase_id>/', views.delete_purchase_order, name='delete_purchase_order'),
    path('admin/purchase_orders/cancel/<int:purchase_id>/', views.cancel_purchase_order, name='cancel_purchase_order'),
    path('admin/purchase_orders/update_stock/<int:purchase_id>/', views.update_received_order_stock, name='update_received_order_stock'),

    path('admin/purchase_items/', views.admin_purchase_items, name='admin_purchase_items'),
    path('admin/purchase_items/add/', views.add_purchase_item, name='add_purchase_item'),
    path('admin/purchase_items/edit/<int:purchase_item_id>/', views.edit_purchase_item, name='edit_purchase_item'),
    path('admin/purchase_items/delete/<int:purchase_item_id>/', views.delete_purchase_item, name='delete_purchase_item'),

    path('admin/suppliers/', views.admin_suppliers, name='admin_suppliers'),
    path('admin/suppliers/add/', views.admin_add_supplier, name='admin_add_supplier'),
    path('admin/suppliers/edit/<int:supplier_id>/', views.edit_supplier, name='edit_supplier'),
    path('admin/suppliers/delete/<int:supplier_id>/', views.delete_supplier, name='delete_supplier'),

    path('admin/inventory/', views.admin_inventory, name='admin_inventory'),

    path('admin/settings/', views.admin_settings, name='admin_settings'),


    # Inventory Manager URLs
    path('inventory/dashboard/', views.inventory_dashboard, name='inventory_dashboard'),
    path('inventory/products/', views.inventory_products, name='inventory_products'),
    path('inventory/products/add/', views.inventory_add_product, name='inventory_add_product'),
    path('inventory/products/edit/<str:product_id>/', views.inventory_edit_product, name='inventory_edit_product'),
    path('inventory/products/delete/<str:product_id>/', views.inventory_delete_product, name='inventory_delete_product'),
    
    path('inventory/categories/', views.category_list, name='category_list'),
    path('inventory/categories/add/', views.add_category, name='add_category'),
    path('inventory/categories/<int:category_id>/', views.get_category_details, name='get_category_details'),
    path('inventory/categories/edit/<int:category_id>/', views.edit_category, name='edit_category'),
    path('inventory/categories/delete/<int:category_id>/', views.delete_category, name='delete_category'),
    
    path('inventory/suppliers/', views.supplier_list, name='supplier_list'),
    path('inventory/suppliers/add/', views.add_supplier, name='add_supplier'),
    path('inventory/suppliers/<int:supplier_id>/', views.get_supplier_details, name='get_supplier_details'),
    path('inventory/suppliers/<int:supplier_id>/edit/', views.edit_supplier, name='edit_supplier'),
    path('inventory/suppliers/<int:supplier_id>/deactivate/', views.deactivate_supplier, name='deactivate_supplier'),
    path('inventory/suppliers/<int:supplier_id>/activate/', views.activate_supplier, name='activate_supplier'),
    path('inventory/purchase-orders/', views.purchase_orders, name='purchase_orders'),
    path('inventory/purchase-orders/add/', views.inventory_manager_add_purchase_order, name='inventory_manager_add_purchase_order'),
    path('inventory/stock-adjustments/', views.stock_adjustments, name='stock_adjustments'),
    path('inventory/stock-adjustments/add/', views.add_stock_adjustment, name='add_stock_adjustment'),
    path('inventory/stock-adjustments/<int:adjustment_id>/', views.get_stock_adjustment, name='get_stock_adjustment'),
    path('inventory/reports/', views.inventory_reports, name='inventory_reports'),

    #POS URLs
    path('pos/dashboard/', views.pos_dashboard, name='pos_dashboard'),
    path('pos/analytics/', views.analytics, name='analytics'),
    path('pos/sales-report/', views.pos_sales_report, name='pos_sales_report'),
    path('pos/view-inventory/', views.view_inventory, name='view_inventory'),
    path('pos/receipts/', views.pos_receipts, name='pos_receipts'),
    path('pos/get-product/<str:product_id>/', views.get_product_details, name='get_product_details'),
    path('pos/save-sale/', views.save_sale, name='save_sale'),
    path('pos/get-daily-sales/', views.get_daily_sales, name='get_daily_sales'),
    path('pos/get-category-sales/', views.get_category_sales, name='get_category_sales'),
    path('pos/get-top-products/', views.get_top_products, name='get_top_products'),
]
