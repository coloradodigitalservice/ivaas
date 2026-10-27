"""Provide a URL configuration for example webhook adapter tests."""

from django.urls import include, path

urlpatterns = [path("api/", include("example_webhook_adapter.urls"))]
