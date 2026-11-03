"""Mount the DPW VMI adapter for tests without reloading the main URLconf."""

from django.urls import include, path

urlpatterns = [path("api/", include("dpw_vmi_adapter.urls"))]
