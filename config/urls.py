from django.urls import path
from ninja import NinjaAPI
from applications.api import router as apps_router
from accounts.api import router as auth_router, admin_router

api = NinjaAPI(title="Workflow Tracker API", version="1.0.0")
api.add_router("/applications", apps_router)
api.add_router("/auth", auth_router)
api.add_router("/admin", admin_router)

urlpatterns = [
    path("api/", api.urls),
]
