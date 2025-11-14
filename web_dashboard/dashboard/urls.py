from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

# Namespace for reversing: include(..., namespace='dashboard') expects this
app_name = 'dashboard'

urlpatterns = [
    # Dashboard root
    path('', views.dashboard, name='dashboard'),

    # Authentication
    path('login/', views.external_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # Rooms (grouped under /rooms/)
    path('rooms/create/', views.create_room, name='create_room'),
    path('rooms/<int:room_id>/deactivate/', views.deactivate_room, name='deactivate_room'),

    # Questions (grouped under /questions/)
    path('questions/create/', views.create_question, name='create_question'),
    path('questions/delete/<int:question_id>/', views.delete_question, name='delete_question'),
    path('questions/toggle_active/<int:question_id>/', views.toggle_question_active, name='toggle_question_active'),

    # Schedule and availability (grouped under /schedule/)
    path('schedule/', views.tutoring_schedule, name='tutoring_schedule'),
    path('schedule/create/', views.create_availability, name='create_availability'),
    path('schedule/delete/', views.delete_availability, name='delete_availability'),
    path('schedule/edit/', views.edit_availability, name='edit_availability'),
]
