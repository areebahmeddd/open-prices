from django.conf import settings
from django.core.validators import ValidationError
from django.db import models
from django.db.models import Count, signals
from django.dispatch import receiver
from django.utils import timezone

from open_prices.common import constants, utils
from open_prices.locations import constants as location_constants
from open_prices.proofs import constants as proof_constants


class ProofQuerySet(models.QuerySet):
    def has_type_price_tag(self):
        return self.filter(type=proof_constants.TYPE_PRICE_TAG)

    def has_type_receipt(self):
        return self.filter(type=proof_constants.TYPE_RECEIPT)

    def has_type_single_shop(self):
        return self.filter(type__in=proof_constants.TYPE_SINGLE_SHOP_LIST)

    def has_prices(self):
        return self.filter(price_count__gt=0)

    def with_stats(self):
        return self.annotate(price_count_annotated=Count("prices", distinct=True))


class Proof(models.Model):
    FILE_FIELDS = ["file_path", "mimetype", "image_thumb_path"]
    UPDATE_FIELDS = ["type", "currency", "date"]
    CREATE_FIELDS = UPDATE_FIELDS + ["location_osm_id", "location_osm_type"]
    DUPLICATE_PRICE_FIELDS = [
        "location_osm_id",
        "location_osm_type",
        "date",
        "currency",
    ]  # "owner"
    FIX_PRICE_FIELDS = ["location", "date", "currency"]

    file_path = models.CharField(blank=True, null=True)
    mimetype = models.CharField(blank=True, null=True)
    type = models.CharField(max_length=20, choices=proof_constants.TYPE_CHOICES)

    image_thumb_path = models.CharField(blank=True, null=True)

    location_osm_id = models.PositiveBigIntegerField(blank=True, null=True)
    location_osm_type = models.CharField(
        max_length=10,
        choices=location_constants.OSM_TYPE_CHOICES,
        blank=True,
        null=True,
    )
    location = models.ForeignKey(
        "locations.Location",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="proofs",
    )
    date = models.DateField(blank=True, null=True)
    currency = models.CharField(
        max_length=3, choices=constants.CURRENCY_CHOICES, blank=True, null=True
    )

    price_count = models.PositiveIntegerField(default=0, blank=True, null=True)

    owner = models.CharField(blank=True, null=True)
    source = models.CharField(blank=True, null=True)

    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(auto_now=True)

    objects = models.Manager.from_queryset(ProofQuerySet)()

    class Meta:
        # managed = False
        db_table = "proofs"
        verbose_name = "Proof"
        verbose_name_plural = "Proofs"

    def clean(self, *args, **kwargs):
        # dict to store all ValidationErrors
        validation_errors = dict()
        # proof rules
        # - date should have the right format & not be in the future
        if self.date:
            if type(self.date) is str:
                validation_errors = utils.add_validation_error(
                    validation_errors,
                    "date",
                    "Parsing error. Expected format: YYYY-MM-DD",
                )
            elif self.date > timezone.now().date():
                validation_errors = utils.add_validation_error(
                    validation_errors,
                    "date",
                    "Should not be in the future",
                )
        # location rules
        # - location_osm_id should be set if location_osm_type is set
        # - location_osm_type should be set if location_osm_id is set
        if self.location_osm_id:
            if not self.location_osm_type:
                validation_errors = utils.add_validation_error(
                    validation_errors,
                    "location_osm_type",
                    "Should be set if `location_osm_id` is filled",
                )
        if self.location_osm_type:
            if not self.location_osm_id:
                validation_errors = utils.add_validation_error(
                    validation_errors,
                    "location_osm_id",
                    "Should be set if `location_osm_type` is filled",
                )
            elif self.location_osm_id in [True, "true", "false", "none", "null"]:
                validation_errors = utils.add_validation_error(
                    validation_errors,
                    "location_osm_id",
                    "Should not be a boolean or an invalid string",
                )
        # return
        if bool(validation_errors):
            raise ValidationError(validation_errors)
        super().clean(*args, **kwargs)

    def set_location(self):
        if self.location_osm_id and self.location_osm_type:
            from open_prices.locations import constants as location_constants
            from open_prices.locations.models import Location

            location, created = Location.objects.get_or_create(
                type=location_constants.TYPE_OSM,
                osm_id=self.location_osm_id,
                osm_type=self.location_osm_type,
            )
            self.location = location

    def save(self, *args, **kwargs):
        self.full_clean()
        self.set_location()
        super().save(*args, **kwargs)

    @property
    def file_path_full(self):
        if self.file_path:
            return str(settings.IMAGES_DIR / self.file_path)
        return None

    @property
    def image_thumb_path_full(self):
        if self.image_thumb_path:
            return str(settings.IMAGES_DIR / self.image_thumb_path)
        return None

    @property
    def is_type_single_shop(self):
        return self.type in proof_constants.TYPE_SINGLE_SHOP_LIST

    def update_price_count(self):
        self.price_count = self.prices.count()
        self.save(update_fields=["price_count"])

    def update_location(self, location_osm_id, location_osm_type):
        old_location = self.location
        # update proof location
        self.location_osm_id = location_osm_id
        self.location_osm_type = location_osm_type
        self.save()
        # update proof's prices location
        for price in self.prices.all():
            price.location_osm_id = location_osm_id
            price.location_osm_type = location_osm_type
            price.save()
        # update old & new location price counts
        self.refresh_from_db()
        new_location = self.location
        if old_location:
            old_location.update_price_count()
        if new_location:
            new_location.update_price_count()

    def set_missing_location_from_prices(self):
        if self.is_type_single_shop and not self.location and self.prices.exists():
            proof_prices_location_list = list(
                self.prices.values_list("location", flat=True).distinct()
            )
            if len(proof_prices_location_list) == 1:
                location = self.prices.first().location
                self.location_osm_id = location.osm_id
                self.location_osm_type = location.osm_type
                self.save()
            else:
                print(
                    "different locations",
                    self,
                    self.prices.count(),
                    proof_prices_location_list,
                )

    def set_missing_date_from_prices(self):
        if self.is_type_single_shop and not self.date and self.prices.exists():
            proof_prices_dates_list = list(
                self.prices.values_list("date", flat=True).distinct()
            )
            if len(proof_prices_dates_list) == 1:
                self.date = self.prices.first().date
                self.save()
            else:
                print(
                    "different dates",
                    self,
                    self.prices.count(),
                    proof_prices_dates_list,
                )

    def set_missing_currency_from_prices(self):
        if self.is_type_single_shop and not self.currency and self.prices.exists():
            proof_prices_currencies_list = list(
                self.prices.values_list("currency", flat=True).distinct()
            )
            if len(proof_prices_currencies_list) == 1:
                self.currency = self.prices.first().currency
                self.save()
            else:
                print(
                    "different currencies",
                    self,
                    self.prices.count(),
                    proof_prices_currencies_list,
                )


@receiver(signals.post_delete, sender=Proof)
def proof_post_delete_remove_images(sender, instance, **kwargs):
    import os

    if instance.file_path_full:
        if os.path.exists(instance.file_path_full):
            os.remove(instance.file_path_full)
    if instance.image_thumb_path_full:
        if os.path.exists(instance.image_thumb_path_full):
            os.remove(instance.image_thumb_path_full)
