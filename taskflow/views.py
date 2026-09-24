from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Case, When, Value, IntegerField, Count, F, OuterRef, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .ai.service import generate_task_suggestions
import json

from .models import Project, Task, ProjectMembership, Notification
from .forms import RegisterForm, ProjectForm, AddMemberForm, UpdateMemberRoleForm, ProjectTaskForm,PersonalTaskForm


class CustomLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def form_invalid(self, form):
        messages.error(self.request, "Invalid email or password. Please try again.")
        login_url = reverse("login")
        next_url = self.request.POST.get("next")
        if next_url:
            login_url = f"{login_url}?{urlencode({'next': next_url})}"
        return redirect(login_url)


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your account was created successfully. You can now sign in.")
            return redirect("login")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form})


def check_and_create_deadline_notifications(user):
    now = timezone.now()
    two_days_later = now + timedelta(days=2)

    urgent_tasks = Task.objects.filter(
        Q(personal_owner=user) | Q(assigned_to=user),
        deadline__isnull=False,
        deadline__gte=now,
        deadline__lte=two_days_later,
    ).exclude(status=Task.Status.DONE)

    for task in urgent_tasks:
        already_notified = Notification.objects.filter(
            user=user,
            task=task,
            message__icontains="deadline is approaching"
        ).exists()

        if not already_notified:
            Notification.objects.create(
                user=user,
                task=task,
                message=f"Reminder: Task '{task.title}' deadline is approaching ({task.deadline.strftime('%b %d, %H:%M')})."
            )

@login_required
def dashboard(request):
    user = request.user
    now = timezone.now()

    check_and_create_deadline_notifications(user)

    unread_count = Notification.objects.filter(user=user, is_read=False).count()
    if unread_count > 0:
        messages.info(request, f"You have {unread_count} unread notification(s).",
                        extra_tags="persistent-notif")

    projects = Project.objects.filter(
        Q(owner=user) | Q(memberships__user=user)
    ).distinct()

    my_tasks = Task.objects.filter(
        Q(personal_owner=user) | Q(assigned_to=user)
    ).distinct()

    context = {
        "todo_count": my_tasks.filter(status=Task.Status.TODO).count(),
        "doing_count": my_tasks.filter(status=Task.Status.DOING).count(),
        "done_count": my_tasks.filter(status=Task.Status.DONE).count(),
        "overdue_count": my_tasks.filter(deadline__lt=now).exclude(status=Task.Status.DONE).count(),
        "recent_tasks": my_tasks.select_related("project", "personal_owner").order_by("-created_at")[:5],
        "recent_projects": projects.order_by("-created_at")[:4],
    }

    return render(request, "dashboard.html", context)


@login_required
def project_list(request):
    check_and_create_deadline_notifications(request.user)

    unread_count = Notification.objects.filter(
        user=request.user, is_read=False
    ).count()
    if unread_count > 0:
        messages.info(
            request,
            f"You have {unread_count} unread notification(s).",
            extra_tags="persistent-notif",
        )

    user_role_subquery = ProjectMembership.objects.filter(
        project=OuterRef("pk"), user=request.user
    ).values("role")[:1]

    projects = (
        Project.objects.filter(
            Q(owner=request.user) | Q(memberships__user=request.user)
        )
        .select_related("owner")
        .annotate(
            user_membership_role=Subquery(user_role_subquery)
        )
        .distinct()
        .order_by("-created_at")
    )

    return render(request, "projects/project_list.html", {"projects": projects})


@login_required
def project_create(request):
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            project.save()
            return redirect("project-detail", project_id=project.id)
    else:
        form = ProjectForm()

    context={
                "form": form,
                "page_title": "Create Project",
                "submit_label": "Create Project",
                "is_edit": False,
            }
    
    return render(request, "projects/project_form.html", context)


@login_required
def project_detail(request, project_id): 
    project = get_object_or_404(
        Project.objects.select_related("owner"), id=project_id
    )

    user_membership = ProjectMembership.objects.filter(
        project=project, user=request.user
    ).first()

    is_owner = (project.owner == request.user)

    if not is_owner and not user_membership:
        raise PermissionDenied("You do not have permission to view this project.")

    is_manager = is_owner or (
        user_membership
        and user_membership.role == ProjectMembership.Role.MANAGER
    )

    now = timezone.now()

    all_project_tasks = project.tasks.all().select_related("assigned_to", "created_by")
    
    total_tasks = all_project_tasks.count()
    done_tasks = all_project_tasks.filter(status=Task.Status.DONE).count()
    overdue_tasks = all_project_tasks.filter(
        deadline__lt=now
    ).exclude(status=Task.Status.DONE).count()
    
    completion_rate = round((done_tasks / total_tasks) * 100) if total_tasks > 0 else 0

    tasks = all_project_tasks.order_by("-created_at")

    status_filter = request.GET.get("status", "")
    priority_filter = request.GET.get("priority", "")
    assigned_filter = request.GET.get("assigned", "")
    search_query = request.GET.get("q", "").strip()

    if status_filter:
        if status_filter == "overdue":
            tasks = tasks.filter(deadline__lt=now).exclude(status=Task.Status.DONE)
        else:
            tasks = tasks.filter(status=status_filter)

    if priority_filter:
        tasks = tasks.filter(priority=priority_filter)

    if assigned_filter:
        if assigned_filter == "me":
            tasks = tasks.filter(assigned_to=request.user)
        elif assigned_filter == "unassigned":
            tasks = tasks.filter(assigned_to__isnull=True)
        else:
            tasks = tasks.filter(assigned_to_id=assigned_filter)

    if search_query:
        tasks = tasks.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query)
        )

    memberships = project.memberships.select_related("user").order_by("joined_at")
    add_member_form = AddMemberForm(project=project) if is_manager else None

    context = {
        "project": project,
        "tasks": tasks,
        "memberships": memberships,
        "is_owner": is_owner,
        "is_manager": is_manager,
        "add_member_form": add_member_form,
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "overdue_tasks": overdue_tasks,
        "completion_rate": completion_rate,
        "current_status": status_filter,
        "current_priority": priority_filter,
        "current_assigned": assigned_filter,
        "search_query": search_query,
        "now": now,
    }
    return render(request, "projects/project_detail.html", context)


@login_required
def project_edit(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if project.owner != request.user:
        raise PermissionDenied("Only the project owner can edit this project.")

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            return redirect("project-detail", project_id=project.id)
    else:
        form = ProjectForm(instance=project)

    context={
                "form": form,
                "project": project,
                "page_title": f"Edit {project.title}",
                "submit_label": "Save Changes",
                "is_edit": True,
            }
    
    return render(
        request,
        "projects/project_form.html",context)

@login_required
@require_POST
def project_task_claim(request, project_id, task_id):
    project = get_object_or_404(Project, id=project_id)
    task = get_object_or_404(Task, id=task_id, project=project)

    role = get_project_role(request.user, project)
    if not role:
        raise PermissionDenied("You are not a member of this project.")

    if task.assigned_to is not None:
        messages.warning(
            request, 
            f'Task "{task.title}" has already been assigned to {task.assigned_to.username}.'
        )
        return redirect("project-detail", project_id=project.id)

    task.assigned_to = request.user
    task.save(update_fields=["assigned_to", "updated_at"])

    messages.success(request, f'You claimed task "{task.title}". It is now in your tasks!')
    return redirect("project-detail", project_id=project.id)

@login_required
def project_delete(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if project.owner != request.user:
        raise PermissionDenied("Only the project owner can delete this project.")

    if request.method == "POST":
        project.delete()
        messages.success(request, f'Project "{project.title}" was successfully deleted.')
        return redirect("project-list")

    return render(request, "projects/project_confirm_delete.html",{"project": project,})


@login_required
@require_POST
def project_add_member(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    user_membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
    if project.owner != request.user and (not user_membership or user_membership.role != ProjectMembership.Role.MANAGER):
        raise PermissionDenied("You do not have permission to add members.")

    form = AddMemberForm(request.POST, project=project)
    if form.is_valid():
        user = form.cleaned_data["user"]
        role = form.cleaned_data["role"]
        ProjectMembership.objects.create(
            project=project,
            user=user,
            role=role,
        )
        if user != request.user:
            Notification.objects.create(
                user=user,
                message=f"You have been added to project '{project.title}' as {role}."
            )
        messages.success(request, f"{user.email} added to project successfully.")
    else:
        for error in form.errors.values():
            messages.error(request, error[0])

    return redirect("project-detail", project_id=project.id)


@login_required
@require_POST
def project_remove_member(request, project_id, membership_id):
    project = get_object_or_404(Project, id=project_id)
    membership = get_object_or_404(ProjectMembership, id=membership_id, project=project)

    user_membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
    is_owner = (project.owner == request.user)
    is_manager = is_owner or (user_membership and user_membership.role == ProjectMembership.Role.MANAGER)

    if not is_manager and membership.user != request.user:
        raise PermissionDenied("You do not have permission to remove this member.")

    if membership.user == project.owner:
        messages.error(request, "The project owner cannot be removed.")
        return redirect("project-detail", project_id=project.id)

    if not is_owner and membership.role == ProjectMembership.Role.MANAGER and membership.user != request.user:
        raise PermissionDenied("Only the project owner can remove managers.")

    membership.delete()
    messages.success(request, "Member was removed successfully.")

    if membership.user == request.user:
        return redirect("project-list")

    return redirect("project-detail", project_id=project.id)


@login_required
@require_POST
def project_update_member_role(request, project_id, membership_id):
    project = get_object_or_404(Project, id=project_id)
    membership = get_object_or_404(ProjectMembership, id=membership_id, project=project)

    if project.owner != request.user:
        raise PermissionDenied("Only the project owner can change member roles.")

    if membership.user == project.owner:
        messages.error(request, "Owner role cannot be changed.")
        return redirect("project-detail", project_id=project.id)

    form = UpdateMemberRoleForm(request.POST, instance=membership)
    if form.is_valid():
        form.save()
        messages.success(request, f"Role for {membership.user.username} updated.")
    else:
        messages.error(request, "Invalid role selected.")

    return redirect("project-detail", project_id=project.id)


def get_project_role(user, project):
    if project.owner == user:
        return ProjectMembership.Role.OWNER
    membership = ProjectMembership.objects.filter(project=project, user=user).first()
    return membership.role if membership else None


@login_required
def project_task_create(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    role = get_project_role(request.user, project)
    if not role:
        raise PermissionDenied("You are not a member of this project.")

    is_privileged = role in [
        ProjectMembership.Role.OWNER,
        ProjectMembership.Role.MANAGER,
    ]

    if request.method == "POST":
        form = ProjectTaskForm(
            request.POST,
            project=project,
            role=role,
        )

        if form.is_valid():
            task = form.save(commit=False)
            task.project = project
            task.created_by = request.user

            if not is_privileged:
                task.assigned_to = request.user

            task.save()

            if task.assigned_to and task.assigned_to != request.user:
                Notification.objects.create(
                    user=task.assigned_to,
                    task=task,
                    message=(
                        f"You have been assigned to task "
                        f"'{task.title}' in project '{project.title}'."
                    ),
                )

            messages.success(
                request,
                f'Task "{task.title}" created successfully.',
            )
            return redirect("project-detail", project_id=project.id)

    else:
        form = ProjectTaskForm(
            project=project,
            role=role,
        )

    context = {
        "form": form,
        "project": project,
        "page_title": f"Create Task in {project.title}",
        "submit_label": "Create Task",
        "is_edit": False,
        "is_personal": False,
    }

    return render(request, "tasks/task_form.html", context)

@login_required
def project_task_edit(request, project_id, task_id):
    project = get_object_or_404(Project, id=project_id)
    task = get_object_or_404(Task, id=task_id, project=project)
    
    role = get_project_role(request.user, project)
    if not role:
        raise PermissionDenied("You are not a member of this project.")

    if not task.can_edit(request.user):
        raise PermissionDenied("You do not have permission to edit this task.")

    is_manager = role in [ProjectMembership.Role.OWNER, ProjectMembership.Role.MANAGER]

    if request.method == "POST":
        form = ProjectTaskForm(
            request.POST, instance=task, project=project, role=role
        )
        old_assigned_to = task.assigned_to
        old_priority = task.priority

        if form.is_valid():
            task = form.save(commit=False)
            if not is_manager:
                task.assigned_to = form.initial.get("assigned_to", task.assigned_to)
            task.save()

            if task.assigned_to and task.assigned_to != old_assigned_to and task.assigned_to != request.user:
                Notification.objects.create(
                    user=task.assigned_to,
                    task=task,
                    message=f"You have been assigned to task '{task.title}' in project '{project.title}'."
                )

            if task.assigned_to and task.priority != old_priority:
                Notification.objects.create(
                    user=task.assigned_to,
                    task=task,
                    message=f"Priority of task '{task.title}' was changed from {old_priority} to {task.priority}."
                )
            messages.success(request, f'Task "{task.title}" updated.')
            return redirect("project-detail", project_id=project.id)
    else:
        initial_data = {}
        if task.deadline:
            initial_data["deadline"] = task.deadline.strftime("%Y-%m-%dT%H:%M")
            
        form = ProjectTaskForm(
            instance=task, project=project, role=role, initial=initial_data
        )

    context = {
        "form": form,
        "project": project,
        "task": task,
        "page_title": f'Edit Task "{task.title}"',
        "submit_label": "Save Changes",
        "is_edit": True,
    }
    return render(request, "tasks/task_form.html", context)


@login_required
def project_task_delete(request, project_id, task_id):
    project = get_object_or_404(Project, id=project_id)
    task = get_object_or_404(Task, id=task_id, project=project)

    role = get_project_role(request.user, project)
    if not role:
        raise PermissionDenied("You are not a member of this project.")

    if not task.can_delete(request.user):
        raise PermissionDenied("You do not have permission to delete this task.")

    if request.method == "POST":
        task_title = task.title
        task.delete()
        messages.success(request, f'Task "{task_title}" was deleted.')
        return redirect("project-detail", project_id=project.id)

    return render(
        request,
        "tasks/task_confirm_delete.html",
        {"task": task, "project": project},
    )


@login_required
@require_POST
def task_update_status(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    new_status = request.POST.get("status")

    if new_status not in Task.Status.values:
        messages.error(request, "Invalid status.")
        return redirect(request.META.get("HTTP_REFERER", "dashboard"))

    if task.personal_owner:
        if task.personal_owner != request.user:
            raise PermissionDenied("You cannot modify this personal task.")
    else:
        role = get_project_role(request.user, task.project)
        if not role:
            raise PermissionDenied("You are not part of this project.")
        if role == ProjectMembership.Role.MEMBER and task.assigned_to != request.user:
            raise PermissionDenied("Members can only update their own assigned tasks.")

    task.status = new_status
    task.save()
    messages.success(request, f'Status of "{task.title}" updated to {task.get_status_display()}.')
    return redirect(request.META.get("HTTP_REFERER", "dashboard"))


@login_required
def task_list(request):
    check_and_create_deadline_notifications(request.user)

    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    if unread_count > 0:
        messages.info(request, f"You have {unread_count} unread notification(s).",
            extra_tags="persistent-notif"
        )
    user = request.user

    task_type = request.GET.get("type", "all")
    status_filter = request.GET.get("status", "")
    priority_filter = request.GET.get("priority", "")
    search_query = request.GET.get("q", "").strip()

    tasks = Task.objects.filter(
        Q(personal_owner=user) | 
        Q(assigned_to=user)
    ).select_related("project", "personal_owner", "assigned_to").distinct()


    if task_type == "personal":
        tasks = tasks.filter(personal_owner=user)
    elif task_type == "project":
        tasks = tasks.filter(project__isnull=False)


    if status_filter in dict(Task.Status.choices):
        tasks = tasks.filter(status=status_filter)


    if priority_filter in dict(Task.Priority.choices):
        tasks = tasks.filter(priority=priority_filter)


    if search_query:
        tasks = tasks.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )


    tasks = tasks.annotate(
        priority_order=Case(
            When(priority=Task.Priority.HIGH, then=Value(1)),
            When(priority=Task.Priority.MEDIUM, then=Value(2)),
            When(priority=Task.Priority.LOW, then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by("priority_order", "deadline", "-created_at")

    context = {
        "tasks": tasks,
        "task_type": task_type,
        "status_filter": status_filter,
        "priority_filter": priority_filter,
        "search_query": search_query,
        "status_choices": Task.Status.choices,
        "priority_choices": Task.Priority.choices,
        "total_count": tasks.count(),
    }
    return render(request, "tasks/task_list.html", context)


@login_required
def personal_task_create(request):
    if request.method == "POST":
        form = PersonalTaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.personal_owner = request.user
            task.assigned_to = request.user
            task.save()
            messages.success(request, f'Personal task "{task.title}" created successfully.')
            return redirect("task-list")
    else:
        form = PersonalTaskForm(user=request.user)

    context = {
        "form": form,
        "page_title": "Create Personal Task",
        "submit_label": "Create Task",
        "is_edit": False,
        "is_personal": True,
    }
    return render(request, "tasks/task_form.html", context)


@login_required
def personal_task_edit(request, task_id):
    task = get_object_or_404(Task, id=task_id, personal_owner=request.user)

    if request.method == "POST":
        form = PersonalTaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, f'Personal task "{task.title}" updated.')
            return redirect("task-list")
    else:
        initial_data = {}
        if task.deadline:
            initial_data["deadline"] = task.deadline.strftime("%Y-%m-%dT%H:%M")
        form = PersonalTaskForm(instance=task, initial=initial_data)

    context = {
        "form": form,
        "task": task,
        "page_title": f'Edit "{task.title}"',
        "submit_label": "Save Changes",
        "is_edit": True,
        "is_personal": True,
    }
    return render(request, "tasks/task_form.html", context)


@login_required
def personal_task_delete(request, task_id):
    task = get_object_or_404(Task, id=task_id, personal_owner=request.user)

    if request.method == "POST":
        title = task.title
        task.delete()
        messages.success(request, f'Personal task "{title}" deleted.')
        return redirect("task-list")

    return render(request, "tasks/task_confirm_delete.html", {"task": task, "is_personal": True})

@login_required
@require_POST
def ai_generate_tasks(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    # Check project access
    if project.owner != request.user:
        membership = ProjectMembership.objects.filter(
            project=project,
            user=request.user,
        ).first()

        if not membership:
            raise PermissionDenied

    project_description = project.description.strip()

    if not project_description:
        return JsonResponse(
            {
                "success": False,
                "error": "Please add a project description first.",
            },
            status=400,
        )

    try:
        suggestions = generate_task_suggestions(
            project_description
        )

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "error": "Unable to generate AI suggestions.",
            },
            status=500,
        )

    return JsonResponse(
        {
            "success": True,
            "suggestions": suggestions,
        }
    )

@login_required
@require_POST
def ai_create_tasks(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    # Check project access
    if project.owner != request.user:
        membership = ProjectMembership.objects.filter(
            project=project,
            user=request.user,
        ).first()

        if not membership:
            raise PermissionDenied

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    suggestions = data.get("suggestions", [])

    if not isinstance(suggestions, list):
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid suggestions data.",
            },
            status=400,
        )

    valid_priorities = {
        Task.Priority.LOW,
        Task.Priority.MEDIUM,
        Task.Priority.HIGH,
    }

    created_tasks = []

    for suggestion in suggestions[:7]:

        if not isinstance(suggestion, dict):
            continue

        title = str(
            suggestion.get("title", "")
        ).strip()

        description = str(
            suggestion.get("description", "")
        ).strip()

        priority = str(
            suggestion.get("priority", Task.Priority.MEDIUM)
        ).upper().strip()

        if not title:
            continue

        if priority not in valid_priorities:
            priority = Task.Priority.MEDIUM

        task = Task(
            project=project,
            title=title[:255],
            description=description,
            priority=priority,
            status=Task.Status.TODO,
            created_by=request.user,
            is_ai_suggested=True,
        )

        task.full_clean()
        task.save()

        created_tasks.append({
            "id": task.id,
            "title": task.title,
        })

    return JsonResponse({
        "success": True,
        "created_tasks": created_tasks,
        "count": len(created_tasks),
    })

@login_required
def notification_list(request):
    check_and_create_deadline_notifications(request.user)

    notifications = Notification.objects.filter(user=request.user).select_related("task").order_by("-created_at")

    return render(request, "notifications/notification_list.html", {"notifications": notifications})


@login_required
@require_POST
def mark_notification_as_read(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.is_read = True
    notif.save()
    return redirect("notification-list")


@login_required
@require_POST
def mark_all_notifications_as_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect("notification-list")


def get_report_period(request):
    period = request.GET.get("period", "all")
    now = timezone.now()

    period_options = {
        "all": {
            "start_date": None,
            "label": "All Time",
        },
        "7": {
            "start_date": now - timedelta(days=7),
            "label": "Last 7 Days",
        },
        "30": {
            "start_date": now - timedelta(days=30),
            "label": "Last 30 Days",
        },
        "month": {
            "start_date": now.replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            ),
            "label": "This Month",
        },
    }

    # Prevent invalid query values.
    if period not in period_options:
        period = "all"

    return (
        period,
        period_options[period]["start_date"],
        period_options[period]["label"],
    )


def apply_period_filter(tasks, start_date):
    if start_date:
        return tasks.filter(created_at__gte=start_date)

    return tasks


def calculate_task_metrics(tasks, now):

    metrics = tasks.aggregate(
        total=Count("id"),

        todo=Count(
            "id",
            filter=Q(status=Task.Status.TODO),
        ),

        doing=Count(
            "id",
            filter=Q(status=Task.Status.DOING),
        ),

        done=Count(
            "id",
            filter=Q(status=Task.Status.DONE),
        ),

        overdue=Count(
            "id",
            filter=(
                Q(deadline__lt=now)
                & ~Q(status=Task.Status.DONE)
            ),
        ),

        completed_with_deadline=Count(
            "id",
            filter=(
                Q(status=Task.Status.DONE)
                & Q(deadline__isnull=False)
                & Q(completed_at__isnull=False)
            ),
        ),

        completed_on_time=Count(
            "id",
            filter=(
                Q(status=Task.Status.DONE)
                & Q(deadline__isnull=False)
                & Q(completed_at__isnull=False)
                & Q(completed_at__lte=F("deadline"))
            ),
        ),
    )

    total = metrics["total"] or 0
    done = metrics["done"] or 0

    completed_with_deadline = (
        metrics["completed_with_deadline"] or 0
    )

    completed_on_time = metrics["completed_on_time"] or 0

    # Percentage of all tasks that are completed.
    metrics["completion_rate"] = (
        round((done / total) * 100)
        if total else 0
    )

    # Percentage of completed tasks that were done before their deadline.
    metrics["on_time_rate"] = (
        round(
            (completed_on_time / completed_with_deadline) * 100
        )
        if completed_with_deadline else 0
    )

    return metrics

@login_required
def performance_report(request):
    user = request.user
    now = timezone.now()

    report_period, start_date, report_period_label = get_report_period(
        request
    )

    all_personal_tasks = Task.objects.filter(
        personal_owner=user
    )

    personal_tasks = apply_period_filter(
        all_personal_tasks,
        start_date,
    )

    personal_metrics = calculate_task_metrics(
        personal_tasks,
        now,
    )

    due_soon_date = now + timedelta(days=3)

    personal_metrics["due_soon"] = all_personal_tasks.filter(
        deadline__gte=now,
        deadline__lte=due_soon_date,
    ).exclude(
        status=Task.Status.DONE
    ).count()

    owned_projects = (
        Project.objects.filter(owner=user)
        .prefetch_related("memberships__user")
        .order_by("-created_at")
    )

    project_reports = []

    for project in owned_projects:
        all_project_tasks = project.tasks.all()

        project_tasks = apply_period_filter(
            all_project_tasks,
            start_date,
        )

        project_metrics = calculate_task_metrics(
            project_tasks,
            now,
        )

        unassigned_count = project_tasks.filter(
            assigned_to__isnull=True
        ).count()

        project_people = {
            project.owner_id: project.owner,
        }

        for membership in project.memberships.all():
            project_people[membership.user_id] = membership.user

        member_stats_queryset = (
            project_tasks
            .filter(assigned_to__isnull=False)
            .values(
                "assigned_to_id",
                "assigned_to__username",
                "assigned_to__email",
            )
            .annotate(
                total=Count("id"),

                todo=Count(
                    "id",
                    filter=Q(status=Task.Status.TODO),
                ),

                doing=Count(
                    "id",
                    filter=Q(status=Task.Status.DOING),
                ),

                done=Count(
                    "id",
                    filter=Q(status=Task.Status.DONE),
                ),

                overdue=Count(
                    "id",
                    filter=(
                        Q(deadline__lt=now)
                        & ~Q(status=Task.Status.DONE)
                    ),
                ),

                completed_with_deadline=Count(
                    "id",
                    filter=(
                        Q(status=Task.Status.DONE)
                        & Q(deadline__isnull=False)
                        & Q(completed_at__isnull=False)
                    ),
                ),

                completed_on_time=Count(
                    "id",
                    filter=(
                        Q(status=Task.Status.DONE)
                        & Q(deadline__isnull=False)
                        & Q(completed_at__isnull=False)
                        & Q(completed_at__lte=F("deadline"))
                    ),
                ),
            )
        )

        stats_by_user_id = {
            item["assigned_to_id"]: item
            for item in member_stats_queryset
        }

        member_reports = []

        for person_id, person in project_people.items():
            stats = stats_by_user_id.get(person_id, {})

            total = stats.get("total", 0)
            done = stats.get("done", 0)

            completed_with_deadline = (
                stats.get("completed_with_deadline", 0)
            )

            completed_on_time = (
                stats.get("completed_on_time", 0)
            )

            member_reports.append({
                "user": person,
                "total": total,
                "todo": stats.get("todo", 0),
                "doing": stats.get("doing", 0),
                "done": done,
                "overdue": stats.get("overdue", 0),
                "completed_on_time": completed_on_time,

                "completion_rate": (
                    round((done / total) * 100)
                    if total else 0
                ),

                "on_time_rate": (
                    round(
                        (
                            completed_on_time
                            / completed_with_deadline
                        ) * 100
                    )
                    if completed_with_deadline else 0
                ),
            })

        member_reports.sort(
            key=lambda member: (
                member["completion_rate"],
                member["on_time_rate"],
            ),
            reverse=True,
        )

        project_reports.append({
            "project": project,
            "metrics": project_metrics,
            "unassigned_count": unassigned_count,
            "member_reports": member_reports,
        })

    context = {
        "personal_metrics": personal_metrics,
        "project_reports": project_reports,

        "report_period": report_period,
        "report_period_label": report_period_label,
    }

    return render(
        request,
        "reports/performance_report.html",
        context,
    )
