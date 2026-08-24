from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Project, ProjectMembership


@receiver(post_save, sender=Project)
def add_owner_as_member(sender, instance, created, **kwargs):
    """Automatically add the project owner as an OWNER member when a project is created."""

    if created:
        ProjectMembership.objects.get_or_create(
            user=instance.owner,
            project=instance,
            defaults={
                "role": ProjectMembership.Role.OWNER,
            },
        )
