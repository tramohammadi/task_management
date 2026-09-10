from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Case, When, Value, IntegerField
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Project, Task, ProjectMembership
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


@login_required
def dashboard(request):
    user = request.user
    now = timezone.now()

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
    projects = (
        Project.objects.filter(
            Q(owner=request.user) | Q(memberships__user=request.user)
        )
        .select_related("owner")
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

    is_owner = project.owner == request.user

    if not is_owner and not user_membership:
        raise PermissionDenied("You do not have permission to view this project.")

    is_manager = is_owner or (
        user_membership
        and user_membership.role == ProjectMembership.Role.MANAGER
    )

    project_tasks = (
        project.tasks.all()
        .select_related("assigned_to")
        .order_by("-created_at")
    )
    memberships = project.memberships.select_related("user").order_by(
        "joined_at"
    )

    add_member_form = AddMemberForm(project=project) if is_manager else None

    context = {
        "project": project,
        "tasks": project_tasks,
        "memberships": memberships,
        "is_owner": is_owner,
        "is_manager": is_manager,
        "add_member_form": add_member_form,
        "total_tasks": project_tasks.count(),
        "done_tasks": project_tasks.filter(status=Task.Status.DONE).count(),
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

    is_manager = role in [ProjectMembership.Role.OWNER, ProjectMembership.Role.MANAGER]

    if request.method == "POST":
        form = ProjectTaskForm(request.POST, project=project, is_manager=is_manager)
        if form.is_valid():
            task = form.save(commit=False)
            task.project = project
            task.created_by = request.user
            # Members can only assign to themselves
            if not is_manager:
                task.assigned_to = request.user
            task.save()
            messages.success(request, f'Task "{task.title}" created successfully.')
            return redirect("project-detail", project_id=project.id)
    else:
        form = ProjectTaskForm(project=project, is_manager=is_manager)

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
            request.POST, instance=task, project=project, is_manager=is_manager
        )
        if form.is_valid():
            task = form.save(commit=False)
            if not is_manager:
                task.assigned_to = form.initial.get("assigned_to", task.assigned_to)
            task.save()
            messages.success(request, f'Task "{task.title}" updated.')
            return redirect("project-detail", project_id=project.id)
    else:
        initial_data = {}
        if task.deadline:
            initial_data["deadline"] = task.deadline.strftime("%Y-%m-%dT%H:%M")
        form = ProjectTaskForm(
            instance=task, project=project, is_manager=is_manager, initial=initial_data
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
