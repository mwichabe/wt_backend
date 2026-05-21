from django.db import models
from django.contrib.auth.models import User


class AdminRequest(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="admin_request")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    reason = models.TextField(blank=True, default="")
    reviewer_note = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_admin_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AdminRequest({self.user.username}, {self.status})"


class Notification(models.Model):
    STATUS_UPDATE = "status_update"
    ADMIN_REQUEST = "admin_request"
    TYPE_CHOICES = [
        (STATUS_UPDATE, "Status Update"),
        (ADMIN_REQUEST, "Admin Request Update"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification({self.user.username}: {self.title})"
