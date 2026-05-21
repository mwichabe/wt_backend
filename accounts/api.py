import datetime
from typing import List, Optional

import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from ninja import Router, Schema
from ninja.security import HttpBearer

from .models import AdminRequest, Notification

router = Router()
admin_router = Router()

_ALG = "HS256"
_TTL = datetime.timedelta(days=7)


# ── Auth helpers ──────────────────────────────────────────

class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALG])
            return User.objects.get(id=payload["user_id"], is_active=True)
        except Exception:
            return None


jwt_auth = JWTAuth()


def get_optional_user(request) -> Optional[User]:
    """Return User from JWT header, or None if absent/invalid."""
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALG])
        return User.objects.get(id=payload["user_id"], is_active=True)
    except Exception:
        return None


def _token(user: User) -> str:
    payload = {
        "user_id": user.id,
        "username": user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "exp": datetime.datetime.now(datetime.timezone.utc) + _TTL,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALG)


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


# ── Schemas ───────────────────────────────────────────────

class RegisterIn(Schema):
    username: str
    email: str
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""


class LoginIn(Schema):
    username: str
    password: str


class UserOut(Schema):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    is_staff: bool
    is_superuser: bool


class AuthOut(Schema):
    token: str
    user: UserOut


class ErrorOut(Schema):
    detail: str


class AdminRequestIn(Schema):
    reason: Optional[str] = ""


class AdminRequestOut(Schema):
    id: int
    username: str
    status: str
    reason: str
    reviewer_note: str
    created_at: str

    @staticmethod
    def resolve_username(obj):
        return obj.user.username

    @staticmethod
    def resolve_created_at(obj):
        return obj.created_at.isoformat()


class NotificationOut(Schema):
    id: int
    type: str
    title: str
    message: str
    is_read: bool
    created_at: str

    @staticmethod
    def resolve_created_at(obj):
        return obj.created_at.isoformat()


class ReviewRequestIn(Schema):
    action: str   # "approve" | "reject"
    reviewer_note: Optional[str] = ""


# ── Auth endpoints ────────────────────────────────────────

@router.post("/register", response={201: AuthOut, 400: ErrorOut}, auth=None)
def register(request, payload: RegisterIn):
    if len(payload.username.strip()) < 3:
        return 400, {"detail": "Username must be at least 3 characters."}
    if len(payload.password) < 6:
        return 400, {"detail": "Password must be at least 6 characters."}
    if User.objects.filter(username__iexact=payload.username).exists():
        return 400, {"detail": "Username is already taken."}
    if payload.email and User.objects.filter(email__iexact=payload.email).exists():
        return 400, {"detail": "An account with that email already exists."}

    user = User.objects.create_user(
        username=payload.username.strip(),
        email=payload.email.strip(),
        password=payload.password,
        first_name=(payload.first_name or "").strip(),
        last_name=(payload.last_name or "").strip(),
    )
    return 201, {"token": _token(user), "user": _user_dict(user)}


@router.post("/login", response={200: AuthOut, 401: ErrorOut}, auth=None)
def login(request, payload: LoginIn):
    username = payload.username.strip()
    try:
        db_user = User.objects.get(username__iexact=username)
        user = authenticate(request, username=db_user.username, password=payload.password)
    except User.DoesNotExist:
        user = None
    if not user:
        return 401, {"detail": "Invalid username or password."}
    return 200, {"token": _token(user), "user": _user_dict(user)}


@router.get("/me", response={200: UserOut, 401: ErrorOut}, auth=jwt_auth)
def me(request):
    return 200, _user_dict(request.auth)


# ── Notifications ─────────────────────────────────────────

@router.get("/notifications", response=List[NotificationOut], auth=jwt_auth)
def list_notifications(request):
    return list(request.auth.notifications.all()[:50])


@router.post("/notifications/read-all", response={200: dict}, auth=jwt_auth)
def mark_all_read(request):
    request.auth.notifications.filter(is_read=False).update(is_read=True)
    return 200, {"ok": True}


# ── Admin-request (user side) ─────────────────────────────

@router.post("/request-admin", response={200: dict, 400: ErrorOut}, auth=jwt_auth)
def request_admin(request, payload: AdminRequestIn):
    user = request.auth
    if user.is_staff or user.is_superuser:
        return 400, {"detail": "You are already an admin."}

    req, created = AdminRequest.objects.get_or_create(user=user)
    if not created:
        if req.status == AdminRequest.PENDING:
            return 400, {"detail": "You already have a pending admin request."}
        # re-apply after rejection
        req.status = AdminRequest.PENDING
        req.reason = payload.reason or ""
        req.reviewer_note = ""
        req.reviewed_by = None
        req.save()
    else:
        req.reason = payload.reason or ""
        req.save()

    # Notify all superusers
    superusers = User.objects.filter(is_superuser=True)
    for su in superusers:
        Notification.objects.create(
            user=su,
            type=Notification.ADMIN_REQUEST,
            title="New Admin Request",
            message=f"{user.username} has requested admin privileges."
            + (f" Reason: {payload.reason}" if payload.reason else ""),
        )
    return 200, {"ok": True}


@router.get("/admin-request-status", response={200: dict, 404: ErrorOut}, auth=jwt_auth)
def admin_request_status(request):
    try:
        req = request.auth.admin_request
        return 200, {
            "status": req.status,
            "reviewer_note": req.reviewer_note,
            "created_at": req.created_at.isoformat(),
        }
    except AdminRequest.DoesNotExist:
        return 404, {"detail": "No admin request found."}


# ── Admin router (staff/superuser only) ───────────────────

@admin_router.get("/stats", response={200: dict, 403: ErrorOut}, auth=jwt_auth)
def admin_stats(request):
    user = request.auth
    if not (user.is_staff or user.is_superuser):
        return 403, {"detail": "Admin access required."}

    from applications.models import Application
    apps = Application.objects.all()
    status_counts = {}
    for app in apps:
        status_counts[app.status] = status_counts.get(app.status, 0) + 1

    pending_requests = AdminRequest.objects.filter(status=AdminRequest.PENDING).count()
    total_users = User.objects.filter(is_active=True).count()

    return 200, {
        "total_applications": apps.count(),
        "status_counts": status_counts,
        "pending_admin_requests": pending_requests,
        "total_users": total_users,
    }


@admin_router.get("/requests", response={200: List[AdminRequestOut], 403: ErrorOut}, auth=jwt_auth)
def list_admin_requests(request):
    user = request.auth
    if not user.is_superuser:
        return 403, {"detail": "Super admin access required."}
    return 200, list(AdminRequest.objects.select_related("user").all())


@admin_router.patch("/requests/{req_id}", response={200: dict, 400: ErrorOut, 403: ErrorOut, 404: ErrorOut}, auth=jwt_auth)
def review_admin_request(request, req_id: int, payload: ReviewRequestIn):
    user = request.auth
    if not user.is_superuser:
        return 403, {"detail": "Super admin access required."}

    try:
        req = AdminRequest.objects.select_related("user").get(id=req_id)
    except AdminRequest.DoesNotExist:
        return 404, {"detail": "Request not found."}

    if req.status != AdminRequest.PENDING:
        return 400, {"detail": "This request has already been reviewed."}

    if payload.action == "approve":
        req.status = AdminRequest.APPROVED
        req.reviewer_note = payload.reviewer_note or ""
        req.reviewed_by = user
        req.save()
        # Grant staff role
        req.user.is_staff = True
        req.user.save()
        Notification.objects.create(
            user=req.user,
            type=Notification.ADMIN_REQUEST,
            title="Admin Request Approved",
            message="Your request to become an admin has been approved. You now have admin privileges.",
        )
        return 200, {"ok": True, "action": "approved"}

    elif payload.action == "reject":
        if not payload.reviewer_note or not payload.reviewer_note.strip():
            return 400, {"detail": "A note is required when rejecting a request."}
        req.status = AdminRequest.REJECTED
        req.reviewer_note = payload.reviewer_note
        req.reviewed_by = user
        req.save()
        Notification.objects.create(
            user=req.user,
            type=Notification.ADMIN_REQUEST,
            title="Admin Request Rejected",
            message=f"Your admin request was not approved. Note: {payload.reviewer_note}",
        )
        return 200, {"ok": True, "action": "rejected"}

    return 400, {"detail": "Action must be 'approve' or 'reject'."}


@admin_router.get("/users", response={200: List[dict], 403: ErrorOut}, auth=jwt_auth)
def list_users(request):
    user = request.auth
    if not (user.is_staff or user.is_superuser):
        return 403, {"detail": "Admin access required."}
    users = User.objects.filter(is_active=True).order_by("username")
    result = []
    for u in users:
        admin_req = None
        try:
            ar = u.admin_request
            admin_req = {"status": ar.status, "created_at": ar.created_at.isoformat()}
        except AdminRequest.DoesNotExist:
            pass
        result.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "is_staff": u.is_staff,
            "is_superuser": u.is_superuser,
            "date_joined": u.date_joined.isoformat(),
            "admin_request": admin_req,
        })
    return 200, result
