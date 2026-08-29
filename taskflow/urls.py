from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("", views.CustomLoginView.as_view(), name="home"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    
    # Projects CRUD
    path("projects/", views.project_list_view, name="project-list"),
    path("projects/create/", views.project_create_view, name="project-create"),
    path("projects/<int:project_id>/", views.project_detail_view, name="project-detail"),
    path("projects/<int:project_id>/edit/", views.project_edit_view, name="project-edit"),
    path("projects/<int:project_id>/delete/", views.project_delete_view, name="project-delete"),
]
