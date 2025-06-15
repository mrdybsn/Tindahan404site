from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('crud', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sale',
            name='transaction_date',
            field=models.DateTimeField(auto_now_add=True, db_column='date'),
        ),
        migrations.AlterField(
            model_name='sale',
            name='cashier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='crud.user'),
        ),
        migrations.AlterField(
            model_name='sale',
            name='discount_type',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AlterField(
            model_name='sale',
            name='discount_value',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AlterField(
            model_name='sale',
            name='vat_amount',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
        migrations.RemoveField(
            model_name='sale',
            name='payment_method',
        ),
        migrations.RemoveField(
            model_name='sale',
            name='customer_name',
        ),
    ] 