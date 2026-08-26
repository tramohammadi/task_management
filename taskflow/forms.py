from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model


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
