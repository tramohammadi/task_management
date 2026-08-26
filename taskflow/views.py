from django.contrib import messages
from django.shortcuts import redirect, render
from .forms import RegisterForm
from urllib.parse import urlencode
from django.contrib.auth import views as auth_views
from django.urls import reverse
from django.contrib.auth.decorators import login_required


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
    return render(
        request,
        "dashboard.html",
    )
