from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Project, ProjectMembership, Task
from django.db.models import Q
from django.core.validators import RegexValidator

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
        min_length=2,
        max_length=30,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z0-9_.]+$',
                message="Username can only contain English letters, numbers, underscores, and dots.",
                code='invalid_username'
            ),
        ],
        widget=forms.TextInput(
            attrs={
                "placeholder": "Choose a username (2-30 characters)",
                "autocomplete": "username",
                "maxlength": "30",
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
                    "maxlength": "50",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-input form-textarea",
                    "placeholder": "Describe the goal of this project...",
                    "rows": 5,
                    "maxlength": "1000",
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


class ProjectTaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "assigned_to", "priority", "status", "deadline"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Task title..."}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-input form-textarea",
                    "placeholder": "Task description...",
                    "rows": 4,
                }
            ),
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "deadline": forms.DateTimeInput(
                attrs={"class": "form-input", "type": "datetime-local"}
            ),
        }

    def __init__(self, *args, **kwargs):
        project = kwargs.pop("project", None)
        user_role = kwargs.pop("role", None)
        super().__init__(*args, **kwargs)

        if project:
            if not self.instance.pk:
                self.instance.project = project

            member_user_ids = ProjectMembership.objects.filter(
                project=project
            ).values_list("user_id", flat=True)

            if user_role == ProjectMembership.Role.OWNER:
                users_qs = User.objects.filter(
                    Q(id__in=member_user_ids) | Q(id=project.owner_id)
                ).distinct()
            elif user_role == ProjectMembership.Role.MANAGER:

                users_qs = User.objects.filter(
                    id__in=member_user_ids
                ).exclude(id=project.owner_id).distinct()
            else:
                users_qs = User.objects.none()

            self.fields["assigned_to"].queryset = users_qs
            self.fields["assigned_to"].empty_label = "Unassigned"

        is_privileged = user_role in [
            ProjectMembership.Role.OWNER,
            ProjectMembership.Role.MANAGER,
        ]
        if not is_privileged:
            self.fields.pop("assigned_to", None)



class PersonalTaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "priority", "status", "deadline"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "What do you need to do?"}),
            "description": forms.Textarea(attrs={"class": "form-input form-textarea", "placeholder": "Add any notes...", "rows": 4}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "deadline": forms.DateTimeInput(attrs={"class": "form-input", "type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        if user and not self.instance.pk:
            self.instance.personal_owner = user
            self.instance.assigned_to = user
