import django_filters
from django.db.models import Q, OuterRef, Subquery
from .models import Report, Sensor, SensorDataLog, Maintenance


class SensorFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="custom_search")
    status = django_filters.CharFilter(method="filter_realtime_status")

    class Meta:
        model = Sensor
        fields = ["is_active", "layout"]

    def filter_realtime_status(self, queryset, name, value):
        # Subquery to get the latest status from logs
        latest_log = (
            SensorDataLog.objects.filter(sensor=OuterRef("pk"))
            .order_by("-timestamp")
            .values("status")[:1]
        )

        queryset = queryset.annotate(current_status=Subquery(latest_log))

        if value == "All":
            return queryset
        # matches "Gas Leak", "Fire", "Warning", etc.
        return queryset.filter(current_status__iexact=value)

    def custom_search(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(Q(id=value) | Q(name__icontains=value))
        return queryset.filter(name__icontains=value)


class MaintenanceFilter(django_filters.FilterSet):
    # 1. Explicitly map fields to their custom methods
    status = django_filters.CharFilter(method="filter_status")
    maintenance_type = django_filters.CharFilter(method="filter_maintenance_type")
    frequency = django_filters.CharFilter(method="filter_frequency")
    search = django_filters.CharFilter(method="custom_search")
    start_date = django_filters.DateFilter(
        field_name="scheduled_date", lookup_expr="date__gte"
    )
    end_date = django_filters.DateFilter(
        field_name="actual_date", lookup_expr="date__lte"
    )

    class Meta:
        model = Maintenance
        # Only list fields that exist on the model or are defined above
        fields = [
            "status",
            "maintenance_type",
            "frequency",
            "scheduled_date",
            "actual_date",
        ]

    # 2. Methods must be indented under the main class, NOT inside the Meta class
    def filter_status(self, queryset, name, value):
        if value.lower() == "all":
            return queryset
        return queryset.filter(status__iexact=value)

    def filter_maintenance_type(self, queryset, name, value):
        if value.lower() == "all":
            return queryset
        return queryset.filter(maintenance_type__iexact=value)

    def filter_frequency(self, queryset, name, value):
        if value.lower() == "all":
            return queryset
        return queryset.filter(frequency__iexact=value)

    def custom_search(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(Q(id=value) | Q(sensor__name__icontains=value))
        return queryset.filter(sensor__name__icontains=value)


class ReportFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(method="filter_status")

    # 1. Use the built-in BooleanFilter (no custom method needed!)
    is_approved = django_filters.BooleanFilter()

    start_date = django_filters.DateFilter(
        field_name="timestamp", lookup_expr="date__gte"
    )
    end_date = django_filters.DateFilter(
        field_name="timestamp", lookup_expr="date__lte"
    )
    search = django_filters.CharFilter(method="custom_search")

    class Meta:
        model = Report
        fields = ["status", "is_approved", "timestamp"]

    def filter_status(self, queryset, name, value):
        if value.lower() == "all":
            return queryset
        return queryset.filter(status__iexact=value)

    # Notice: filter_is_approved has been completely removed!

    def filter_date_range(self, queryset, name, value):
        if "," in value:
            start_date, end_date = value.split(",")
            return queryset.filter(timestamp__range=[start_date, end_date])
        return queryset

    def custom_search(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(
                Q(id=value) | Q(trigger_sensor__name__icontains=value)
            )
        return queryset.filter(trigger_sensor__name__icontains=value)
