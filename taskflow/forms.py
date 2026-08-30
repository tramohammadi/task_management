from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Project, ProjectMembership

User = get_user_model()


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        ),
    )

    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Choose a username",
                "autocomplete": "username",
            }
        ),
    )

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Create a password",
                "autocomplete": "new-password",
            }
        ),
    )

    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Enter your password again",
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta:
        model = User

        fields = (
            "email",
            "username",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )

        return email


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "title",
            "description",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "For example: Software Engineering Project",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-input form-textarea",
                    "placeholder": "Describe the goal of this project...",
                    "rows": 5,
                }
            ),
        }


class AddMemberForm(forms.Form):
    email = forms.EmailField(
        label="Member Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "placeholder": "user@example.com",
            }
        ),
    )
    role = forms.ChoiceField(
        choices=[
            (ProjectMembership.Role.MEMBER, "Member"),
            (ProjectMembership.Role.MANAGER, "Manager"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop("project", None)
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise forms.ValidationError("No user found with this email address.")

        if self.project:
            if self.project.owner == user:
                raise forms.ValidationError("The project owner is already a member.")
            if ProjectMembership.objects.filter(project=self.project, user=user).exists():
                raise forms.ValidationError("This user is already a member of the project.")

        self.cleaned_data["user"] = user
        return email


class UpdateMemberRoleForm(forms.ModelForm):
    class Meta:
        model = ProjectMembership
        fields = ["role"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields["role"].choices = [
            (ProjectMembership.Role.MEMBER, "Member"),
            (ProjectMembership.Role.MANAGER, "Manager"),
        ]
