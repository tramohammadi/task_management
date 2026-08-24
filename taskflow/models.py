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
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="owned_projects",
    )

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

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER,
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "project"],
                name="unique_project_membership",
            )
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

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    deadline = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.TODO,
        db_index=True,
    )

    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
    )

    # Project task: project is set and personal_owner is null.
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tasks",
        null=True,
        blank=True,
    )

    # Personal task: personal_owner is set and project is null.
    personal_owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="personal_tasks",
        null=True,
        blank=True,
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
        null=True,
        blank=True,
    )

    is_ai_suggested = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        project__isnull=False,
                        personal_owner__isnull=True,
                    )
                    | models.Q(
                        project__isnull=True,
                        personal_owner__isnull=False,
                    )
                ),
                name="task_has_project_or_personal_owner",
            )
        ]

        indexes = [
            models.Index(
                fields=["project", "status"],
                name="idx_task_project_status",
            ),
            models.Index(
                fields=["assigned_to", "status"],
                name="idx_task_assigned_status",
            ),
            models.Index(
                fields=["personal_owner", "status"],
                name="idx_task_personal_status",
            ),
        ]

    def clean(self):
        #Validate whether the task is personal or project-based.

        if self.project_id and self.personal_owner_id:
            raise ValidationError(
                "A task cannot belong to both a project and a personal owner."
            )

        if not self.project_id and not self.personal_owner_id:
            raise ValidationError(
                "A task must belong to either a project or a personal owner."
            )

        if self.personal_owner_id:
            if (
                self.assigned_to_id
                and self.assigned_to_id != self.personal_owner_id
            ):
                raise ValidationError(
                    "A personal task can only be assigned to its personal owner."
                )

        if self.project_id and self.assigned_to_id:
            is_project_member = ProjectMembership.objects.filter(
                project_id=self.project_id,
                user_id=self.assigned_to_id,
            ).exists()

            is_project_owner = Project.objects.filter(
                id=self.project_id,
                owner_id=self.assigned_to_id,
            ).exists()

            if not is_project_member and not is_project_owner:
                raise ValidationError(
                    "The assigned user must be a member of the project."
                )

    def save(self, *args, **kwargs):
        #Automatically manage completed_at when the status changes.

        if self.pk:
            previous = (
                Task.objects
                .filter(pk=self.pk)
                .values("status")
                .first()
            )

            if previous:
                previous_status = previous["status"]

                if (
                    self.status == self.Status.DONE
                    and previous_status != self.Status.DONE
                ):
                    self.completed_at = timezone.now()

                elif (
                    self.status != self.Status.DONE
                    and previous_status == self.Status.DONE
                ):
                    self.completed_at = None

        elif self.status == self.Status.DONE:
            # Handle a new task created directly as DONE.
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )

    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["user", "is_read"],
                name="idx_notification_user_read",
            )
        ]

    def __str__(self):
        status = "read" if self.is_read else "unread"
        return f"Notification for {self.user.email} - {status}"
