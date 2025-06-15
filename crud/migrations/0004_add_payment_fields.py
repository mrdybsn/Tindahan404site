from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('crud', '0003_alter_sale_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='amount_paid',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='sale',
            name='change_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ] 