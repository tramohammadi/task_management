from rest_framework import permissions
from .models import ProjectMembership

class IsProjectOwnerOrManager(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        project = obj if hasattr(obj, 'owner') else obj.project
        if project.owner == request.user:
            return True
        membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
        return membership and membership.role == ProjectMembership.Role.MANAGER


class CanEditOrDeleteTask(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.method == 'DELETE':
            return obj.can_delete(request.user)
        return obj.can_edit(request.user)
