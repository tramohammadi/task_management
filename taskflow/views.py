from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Project, Task, ProjectMembership
from .forms import RegisterForm, ProjectForm, AddMemberForm, UpdateMemberRoleForm


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


def register_view(request):
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
def dashboard_view(request):
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
def project_list_view(request):
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
def project_create_view(request):
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
def project_detail_view(request, project_id): 
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
def project_edit_view(request, project_id):
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
def project_delete_view(request, project_id):
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
def project_add_member_view(request, project_id):
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
def project_remove_member_view(request, project_id, membership_id):
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
def project_update_member_role_view(request, project_id, membership_id):
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