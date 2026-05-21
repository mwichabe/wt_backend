from django.db import models
from django.contrib.auth.models import User
import uuid


class ApplicationType(models.TextChoices):
    RECORDATION = "Recordation"
    RENEWAL = "Renewal"
    CHANGE_OF_OWNERSHIP = "Change of Ownership"
    CHANGE_OF_NAME = "Change of Name"
    DISCONTINUATION = "Discontinuation"


class ApplicationStatus(models.TextChoices):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    NEED_MORE_INFORMATION = "Need More Information"
    APPROVED = "Approved"
    REJECTED = "Rejected"


def generate_tracking_number():
    return f"APP-{uuid.uuid4().hex[:8].upper()}"


class Application(models.Model):
    tracking_number = models.CharField(max_length=20, unique=True, default=generate_tracking_number)
    applicant_name = models.CharField(max_length=255)
    applicant_email = models.EmailField()
    company_name = models.CharField(max_length=255)
    application_type = models.CharField(max_length=50, choices=ApplicationType.choices)
    description = models.TextField()
    status = models.CharField(max_length=30, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT)
    reviewer_comment = models.TextField(blank=True, default="")
    submitted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submitted_applications",
    )
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_applications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tracking_number} - {self.applicant_name}"
