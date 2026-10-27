"""Route requests to the example webhook adapter API."""

from django.urls import path

from example_webhook_adapter.api import api

urlpatterns = [path("example-webhook/v1/", api.urls)]
