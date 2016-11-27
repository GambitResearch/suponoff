from django.conf.urls import include, url

urlpatterns = [
    url(r'^', include('suponoff.urls')),
]
