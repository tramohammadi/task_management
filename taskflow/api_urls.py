from django.urls import path
from . import api_views

urlpatterns = [
    # Auth
    path('auth/register/', api_views.RegisterAPIView.as_view(), name='api-register'),
    path('auth/login/', api_views.CustomAuthToken.as_view(), name='api-login'),
    path('auth/profile/', api_views.UserProfileAPIView.as_view(), name='api-profile'),

    # Projects
    path('projects/', api_views.ProjectListCreateAPIView.as_view(), name='api-project-list'),
    path('projects/<int:pk>/', api_views.ProjectDetailAPIView.as_view(), name='api-project-detail'),

    # Tasks
    path('tasks/', api_views.TaskListCreateAPIView.as_view(), name='api-task-list'),
    path('tasks/<int:pk>/', api_views.TaskDetailAPIView.as_view(), name='api-task-detail'),
    path('tasks/<int:pk>/status/', api_views.TaskUpdateStatusAPIView.as_view(), name='api-task-status'),

    # Dashboard & AI
    path('dashboard/stats/', api_views.DashboardStatsAPIView.as_view(), name='api-dashboard-stats'),
    path('ai/suggest-tasks/', api_views.AISuggestTasksAPIView.as_view(), name='api-ai-suggest'),
]
