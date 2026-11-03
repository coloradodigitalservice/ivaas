"""Route requests to the DPW VMI adapter API."""

from django.urls import path

from dpw_vmi_adapter.api import api

urlpatterns = [path("", api.urls)]
