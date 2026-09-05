from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

# urls.py

urlpatterns = [
    path("", views.CustomLoginView.as_view(), name="home"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("register/", views.register, name="register"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    
    # Projects CRUD
    path("projects/", views.project_list, name="project-list"),
    path("projects/create/", views.project_create, name="project-create"),
    path("projects/<int:project_id>/", views.project_detail, name="project-detail"),
    path("projects/<int:project_id>/edit/", views.project_edit, name="project-edit"),
    path("projects/<int:project_id>/delete/", views.project_delete, name="project-delete"),

    # Member Management
    path("projects/<int:project_id>/members/add/", views.project_add_member, name="project-add-member"),
    path("projects/<int:project_id>/members/<int:membership_id>/remove/", views.project_remove_member, name="project-remove-member"),
    path("projects/<int:project_id>/members/<int:membership_id>/update-role/", views.project_update_member_role, name="project-update-member-role"),

    # Project Tasks CRUD
    path("projects/<int:project_id>/tasks/create/", views.project_task_create, name="project-task-create"),
    path("projects/<int:project_id>/tasks/<int:task_id>/edit/", views.project_task_edit, name="project-task-edit"),
    path("projects/<int:project_id>/tasks/<int:task_id>/delete/", views.project_task_delete, name="project-task-delete"),

    # Personal Tasks & Main Tasks Page
    path("tasks/", views.task_list, name="task-list"),
    path("tasks/create-personal/", views.personal_task_create, name="personal-task-create"),
    path("tasks/<int:task_id>/edit-personal/", views.personal_task_edit, name="personal-task-edit"),
    path("tasks/<int:task_id>/delete-personal/", views.personal_task_delete, name="personal-task-delete"),

    # Quick Status Update (Works for both personal and project tasks)
    path("tasks/<int:task_id>/status/", views.task_update_status, name="task-update-status"),
]

