from django.contrib.auth import views as auth_views
from django.urls import path
from .views import (
    CustomLoginView,
    dashboard_view,
    register_view,
)


urlpatterns = [
    path(
        "",
        CustomLoginView.as_view(),
        name="home",
    ),

    path(
        "login/",
        CustomLoginView.as_view(),
        name="login",
    ),

    path(
        "register/",
        register_view,
        name="register",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path(
    "dashboard/",
    dashboard_view,
    name="dashboard",
),

]
