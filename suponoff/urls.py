from django.conf.urls import include, url

from . import views

urlpatterns = [
    url(r'^$', views.home, {'template_name': 'suponoff/index.html'},
        name='suponoff_home'),
    url(r'^action$', views.action, name='suponoff_action'),
    url(r'^data$', views.get_data, name='suponoff_data'),
    url(r'^data/program-logs$', views.get_program_logs,
        name='suponoff_program_logs'),
]
