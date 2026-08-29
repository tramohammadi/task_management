from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import Project, Task
from .forms import RegisterForm, ProjectForm


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
        Project.objects.select_related("owner"),
        Q(owner=request.user) | Q(memberships__user=request.user),
        id=project_id
    )

    project_tasks = project.tasks.all().select_related("assigned_to").order_by("-created_at")

    is_owner = (project.owner == request.user)

    context={
            "project": project,
            "tasks": project_tasks,
            "is_owner": is_owner,
            "total_tasks": project_tasks.count(),
            "done_tasks": project_tasks.filter(status=Task.Status.DONE).count(),
        }
    return render(request, "projects/project_detail.html",context)


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
