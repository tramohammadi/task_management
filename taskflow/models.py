from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email


class Project(models.Model):
    title = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_projects")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MANAGER = "MANAGER", "Manager"
        MEMBER = "MEMBER", "Member"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "project"], name="unique_project_membership")
        ]

    def __str__(self):
        return f"{self.user.email} - {self.project.title} ({self.role})"


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "TODO", "To Do"
        DOING = "DOING", "Doing"
        DONE = "DONE", "Done"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    title = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks", null=True, blank=True)
    personal_owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="personal_tasks", null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="assigned_tasks", null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="created_tasks", null=True, blank=True)

    is_ai_suggested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(project__isnull=False, personal_owner__isnull=True)
                    | models.Q(project__isnull=True, personal_owner__isnull=False)
                ),
                name="task_has_project_or_personal_owner",
            )
        ]
        indexes = [
            models.Index(fields=["project", "status"], name="idx_task_project_status"),
            models.Index(fields=["assigned_to", "status"], name="idx_task_assigned_status"),
            models.Index(fields=["personal_owner", "status"], name="idx_task_personal_status"),
            models.Index(fields=["created_by"], name="idx_task_created_by"),
        ]

    def clean(self):
        if self.project_id and self.personal_owner_id:
            raise ValidationError("A task cannot belong to both a project and a personal owner.")

        if not self.project_id and not self.personal_owner_id:
            raise ValidationError("A task must belong to either a project or a personal owner.")

        if self.personal_owner_id:
            if self.assigned_to_id and self.assigned_to_id != self.personal_owner_id:
                raise ValidationError("A personal task can only be assigned to its personal owner.")
            if self.created_by_id and self.created_by_id != self.personal_owner_id:
                raise ValidationError("A personal task must be created by its personal owner.")

        if self.project_id:
            if self.assigned_to_id:
                is_member = ProjectMembership.objects.filter(project_id=self.project_id, user_id=self.assigned_to_id).exists()
                is_owner = Project.objects.filter(id=self.project_id, owner_id=self.assigned_to_id).exists()
                if not is_member and not is_owner:
                    raise ValidationError("The assigned user must be a member or owner of the project.")

            if self.created_by_id:
                is_creator_member = ProjectMembership.objects.filter(project_id=self.project_id, user_id=self.created_by_id).exists()
                is_creator_owner = Project.objects.filter(id=self.project_id, owner_id=self.created_by_id).exists()
                if not is_creator_member and not is_creator_owner:
                    raise ValidationError("The creator must be a member or owner of the project.")

    def save(self, *args, **kwargs):
        if self.pk:
            prev = Task.objects.filter(pk=self.pk).values("status").first()
            if prev:
                prev_status = prev["status"]
                if self.status == self.Status.DONE and prev_status != self.Status.DONE:
                    self.completed_at = timezone.now()
                elif self.status != self.Status.DONE and prev_status == self.Status.DONE:
                    self.completed_at = None
        elif self.status == self.Status.DONE:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def is_personal(self):
        return self.personal_owner_id is not None

    @property
    def is_project(self):
        return self.project_id is not None

    @property
    def is_overdue(self):
        return bool(self.deadline and self.status != self.Status.DONE and self.deadline < timezone.now())

    def can_delete(self, user):
        if not user or not user.is_authenticated:
            return False
        if self.is_personal:
            return self.personal_owner_id == user.id
        if self.is_project:
            return (
                self.created_by_id == user.id
                or self.project.owner_id == user.id
                or ProjectMembership.objects.filter(
                    project_id=self.project_id, user_id=user.id, role=ProjectMembership.Role.MANAGER
                ).exists()
            )
        return False

    def can_edit(self, user):
        return self.can_delete(user)

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"], name="idx_notification_user_read")
        ]

    def __str__(self):
        status = "read" if self.is_read else "unread"
        return f"Notification for {self.user.email} - {status}"
