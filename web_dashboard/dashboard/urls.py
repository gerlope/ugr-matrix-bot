from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.external_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('create_room/', views.create_room, name='create_room'),
    path('deactivate-room/<int:room_id>/', views.deactivate_room, name='deactivate_room'),
    path('questions/toggle_active/<int:question_id>/', views.toggle_question_active, name='toggle_question_active'),
    path('questions/create/', views.create_question, name='create_question'),
    path('questions/delete/<int:question_id>/', views.delete_question, name='delete_question'),
]
