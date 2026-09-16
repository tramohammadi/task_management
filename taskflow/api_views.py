from rest_framework import generics, status, views, permissions
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from django.db.models import Q, Count
from django.utils import timezone
from django.shortcuts import get_object_or_404

from .models import Project, Task, User
from .serializers import (
    UserSerializer, RegisterSerializer, ProjectSerializer, TaskSerializer
)
from .api_permissions import IsProjectOwnerOrManager, CanEditOrDeleteTask


class RegisterAPIView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "user": UserSerializer(user).data,
            "token": token.key
        }, status=status.HTTP_201_CREATED)


class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        })


class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ProjectListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        user = self.request.user
        return Project.objects.filter(
            Q(owner=user) | Q(memberships__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ProjectDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsProjectOwnerOrManager]

    def get_queryset(self):
        user = self.request.user
        return Project.objects.filter(
            Q(owner=user) | Q(memberships__user=user)
        ).distinct()


class TaskListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = TaskSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Task.objects.filter(
            Q(personal_owner=user) | Q(assigned_to=user) | Q(project__owner=user) | Q(project__memberships__user=user)
        ).distinct()

        task_type = self.request.query_params.get('type')
        status_param = self.request.query_params.get('status')
        priority_param = self.request.query_params.get('priority')
        project_id = self.request.query_params.get('project')
        search = self.request.query_params.get('search')

        if task_type == 'personal':
            qs = qs.filter(personal_owner=user)
        elif task_type == 'project':
            qs = qs.filter(project__isnull=False)

        if status_param:
            qs = qs.filter(status=status_param)
        if priority_param:
            qs = qs.filter(priority=priority_param)
        if project_id:
            qs = qs.filter(project_id=project_id)
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

        return qs

    def perform_create(self, serializer):
        is_personal = serializer.validated_data.get('project') is None
        if is_personal:
            serializer.save(created_by=self.request.user, personal_owner=self.request.user, assigned_to=self.request.user)
        else:
            serializer.save(created_by=self.request.user)


class TaskDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated, CanEditOrDeleteTask]

    def get_queryset(self):
        user = self.request.user
        return Task.objects.filter(
            Q(personal_owner=user) | Q(assigned_to=user) | Q(project__owner=user) | Q(project__memberships__user=user)
        ).distinct()


class TaskUpdateStatusAPIView(views.APIView):
    def patch(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        new_status = request.data.get("status")

        if new_status not in Task.Status.values:
            return Response({"error": "Invalid status value."}, status=status.HTTP_400_BAD_REQUEST)

        if task.personal_owner and task.personal_owner != request.user:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        
        task.status = new_status
        task.save()
        return Response(TaskSerializer(task).data)


class DashboardStatsAPIView(views.APIView):
    def get(self, request):
        user = request.user
        now = timezone.now()
        my_tasks = Task.objects.filter(Q(personal_owner=user) | Q(assigned_to=user)).distinct()

        data = {
            "total_tasks": my_tasks.count(),
            "todo_count": my_tasks.filter(status=Task.Status.TODO).count(),
            "doing_count": my_tasks.filter(status=Task.Status.DOING).count(),
            "done_count": my_tasks.filter(status=Task.Status.DONE).count(),
            "overdue_count": my_tasks.filter(deadline__lt=now).exclude(status=Task.Status.DONE).count(),
        }
        return Response(data)


# --- AI SUGGESTION FEATURE API ---
class AISuggestTasksAPIView(views.APIView):
    def post(self, request):
        prompt = request.data.get("prompt", "")
        if not prompt:
            return Response({"error": "Prompt is required."}, status=status.HTTP_400_BAD_REQUEST)

        suggested_tasks = [
            {"title": "Database Schema Design", "priority": "HIGH"},
            {"title": "Backend API Development", "priority": "HIGH"},
            {"title": "Frontend UI Implementation", "priority": "MEDIUM"},
            {"title": "Authentication & Authorization Setup", "priority": "HIGH"},
            {"title": "Automated & Manual Testing", "priority": "MEDIUM"},
            {"title": "Deployment & Documentation", "priority": "LOW"},
        ]
        return Response({
            "prompt": prompt,
            "suggested_tasks": suggested_tasks
        })
