from django.contrib import messages
from django.shortcuts import redirect, render
from urllib.parse import urlencode
from django.contrib.auth import views as auth_views
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone

from .models import Project, Task
from .forms import RegisterForm

# Create your views here.

class CustomLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Invalid email or password. Please try again.",
        )

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

            messages.success(
                request,
                "Your account was created successfully. You can now sign in.",
            )

            return redirect("login")

    else:
        form = RegisterForm()

    return render(
        request,
        "registration/register.html",
        {
            "form": form,
        },
    )

@login_required
def dashboard_view(request):
    user = request.user
    now = timezone.now()

    # Projects where the user is the owner or a member.
    projects = (
        Project.objects.filter(
            Q(owner=user) | Q(memberships__user=user)
        )
        .distinct()
    )

    # Personal tasks owned by the user + project tasks assigned to the user.
    my_tasks = Task.objects.filter(
        Q(personal_owner=user) | Q(assigned_to=user)
    ).distinct()

    context = {
        "todo_count": my_tasks.filter(
            status=Task.Status.TODO
        ).count(),

        "doing_count": my_tasks.filter(
            status=Task.Status.DOING
        ).count(),

        "done_count": my_tasks.filter(
            status=Task.Status.DONE
        ).count(),

        "overdue_count": my_tasks.filter(
            deadline__lt=now,
        ).exclude(
            status=Task.Status.DONE
        ).count(),

        "recent_tasks": my_tasks.select_related(
            "project",
            "personal_owner",
        ).order_by("-created_at")[:5],

        "recent_projects": projects.order_by(
            "-created_at"
        )[:4],
    }

    return render(
        request,
        "dashboard.html",
        context,
    )
