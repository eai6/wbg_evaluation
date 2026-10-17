from django.urls import path

from assistant import views as assistant_views
from explorer import views

urlpatterns = [
    path("", views.home, name="home"),
    path("outcomes/<slug:slug>/", views.outcome, name="outcome"),
    path("api/outcomes/<int:outcome_id>/data", views.outcome_data, name="outcome_data"),
    path("api/chat", assistant_views.chat, name="chat"),
    path("api/route", assistant_views.route_home, name="route_home"),
    path("api/artifacts/<str:artifact_id>.ipynb", assistant_views.notebook, name="artifact_notebook"),
    path("api/artifacts/<str:artifact_id>/deck", assistant_views.deck, name="artifact_deck"),
    path("api/health", assistant_views.health, name="health"),
]
