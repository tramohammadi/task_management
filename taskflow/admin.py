from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    User,
    Project,
    ProjectMembership,
    Task,
    Notification,
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    list_display = (
        "email",
        "username",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "date_joined",
    )

    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
        "date_joined",
    )

    search_fields = (
        "email",
        "username",
        "first_name",
        "last_name",
    )

    ordering = ("email",)

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    fieldsets = (
        (
            "Login Information",
            {
                "fields": (
                    "email",
                    "username",
                    "password",
                )
            },
        ),
        (
            "Personal Information",
            {
                "fields": (
                    "first_name",
                    "last_name",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important Dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                )
            },
        ),
    )

    readonly_fields = (
        "last_login",
        "date_joined",
    )


class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 1
    show_change_link = True

    autocomplete_fields = (
        "user",
    )

    fields = (
        "user",
        "role",
        "joined_at",
    )

    readonly_fields = (
        "joined_at",
    )


class ProjectTaskInline(admin.TabularInline):
    model = Task
    extra = 0
    show_change_link = True

    autocomplete_fields = (
        "assigned_to",
    )

    fields = (
        "title",
        "assigned_to",
        "status",
        "priority",
        "deadline",
        "is_ai_suggested",
        "completed_at",
    )

    readonly_fields = (
        "completed_at",
    )


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "created_at",
        "updated_at",
        "membership_count",
        "task_count",
    )

    list_filter = (
        "created_at",
        "updated_at",
    )

    search_fields = (
        "title",
        "description",
        "owner__email",
        "owner__username",
    )

    autocomplete_fields = (
        "owner",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = (
        ProjectMembershipInline,
        ProjectTaskInline,
    )

    ordering = (
        "-created_at",
    )

    @admin.display(description="Number of Members")
    def membership_count(self, obj):
        return obj.memberships.count()

    @admin.display(description="Number of Tasks")
    def task_count(self, obj):
        return obj.tasks.count()


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "project",
        "role",
        "joined_at",
    )

    list_filter = (
        "role",
        "joined_at",
    )

    search_fields = (
        "user__email",
        "user__username",
        "project__title",
    )

    autocomplete_fields = (
        "user",
        "project",
    )

    readonly_fields = (
        "joined_at",
    )

    ordering = (
        "joined_at",
    )


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "task_type",
        "project",
        "personal_owner",
        "assigned_to",
        "status",
        "priority",
        "deadline",
        "is_ai_suggested",
        "completed_at",
        "created_at",
    )

    list_filter = (
        "status",
        "priority",
        "is_ai_suggested",
        "deadline",
        "completed_at",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "project__title",
        "personal_owner__email",
        "personal_owner__username",
        "assigned_to__email",
        "assigned_to__username",
    )

    autocomplete_fields = (
        "project",
        "personal_owner",
        "assigned_to",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "completed_at",
    )

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "title",
                    "description",
                    "status",
                    "priority",
                )
            },
        ),
        (
            "Task Ownership",
            {
                "fields": (
                    "project",
                    "personal_owner",
                    "assigned_to",
                )
            },
        ),
        (
            "Scheduling",
            {
                "fields": (
                    "deadline",
                    "completed_at",
                )
            },
        ),
        (
            "System Information",
            {
                "fields": (
                    "is_ai_suggested",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    ordering = (
        "-created_at",
    )

    @admin.display(description="Task Type")
    def task_type(self, obj):
        if obj.project_id:
            return "Project Task"

        if obj.personal_owner_id:
            return "Personal Task"

        return "Invalid"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "short_message",
        "task",
        "is_read",
        "created_at",
    )

    list_filter = (
        "is_read",
        "created_at",
    )

    search_fields = (
        "user__email",
        "user__username",
        "message",
        "task__title",
    )

    autocomplete_fields = (
        "user",
        "task",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = (
        "-created_at",
    )


    @admin.display(description="Message")
    def short_message(self, obj):
        if len(obj.message) > 70:
            return f"{obj.message[:70]}..."

        return obj.message
