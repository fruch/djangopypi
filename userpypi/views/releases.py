from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.forms.models import inlineformset_factory
from django.http import Http404
from django.views.generic import ListView, DetailView
from django.views.generic import create_update
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext

from userpypi.decorators import user_maintains_package
from userpypi.models import Package, Release, Distribution
from userpypi.forms import ReleaseForm, DistributionUploadForm
from userpypi.settings import METADATA_FORMS
from userpypi.utils import get_class

class ReleaseOwnerObjectMixin(object):
    def get_context_data(self, **kwargs):
        context = super(ReleaseOwnerObjectMixin, self).get_context_data(**kwargs)
        context['owner'] = self.get_owner()
        context['is_owner'] = self.owner == self.request.user.username
        return context
    
    def get_owner(self):
        """
        Set the owner user object
        """
        owner = getattr(self, 'owner')
        if owner and issubclass(owner.__class__, User):
            return owner
        owner = self.kwargs.get('owner', None)
        if owner is not None:
            try:
                self.owner = User.objects.get(username=owner)
            except User.DoesNotExist:
                raise Http404
        else:
            raise Http404
        return self.owner
    
    def get_queryset(self):
        """
        Filter the queryset based on whether or not the requesting user is
        the owner of the requested objects
        """
        if self.request.user != self.get_owner():
            if self.owner.profile.organization:
                params = dict(package__owner__username=self.owner)
            else:
                params = dict(package__owner=self.request.user, private=False)
        return self.model.objects.filter(**params)


class ReleaseListView(ReleaseOwnerObjectMixin, ListView):
    model = Release
    context_object_name = 'release_list'
    simple = False
    owner = None
    
    def get_template_names(self):
        """
        Returns a list of template names to be used for the request. Must return
        a list. May not be called if render_to_response is overridden.
        """
        if self.simple:
            return ['userpypi/release_list_simple.html']
        else:
            return ['userpypi/release_list.html']
        

class ReleaseDetailView(ReleaseOwnerObjectMixin, DetailView):
    model = Release
    context_object_name = 'release'
    doap = False
    owner = None
    
    def render_to_response(self, context, **response_kwargs):
        """
        Returns a response with a template rendered with the given context.
        """
        if self.doap:
            response_kwargs['mimetype'] = 'text/xml'
        
        return super(ReleaseDetailView, self).render_to_response(context, **response_kwargs)
    
    def get_object(self):
        package = self.kwargs.get('package', None)
        try:
            queryset = self.get_queryset().filter(package__name=package)
            obj = queryset.get()
        except ObjectDoesNotExist:
            raise Http404(_(u"No %(verbose_name)s found matching the query") %
                          {'verbose_name': queryset.model._meta.verbose_name})
        return obj
    
    def get_template_names(self):
        """
        Returns a list of template names to be used for the request. Must return
        a list. May not be called if render_to_response is overridden.
        """
        self.doap = 'doap' in self.kwargs and self.kwargs['doap']
        
        if self.doap:
            return ['userpypi/release_doap.xml']
        else:
            return ['userpypi/release_detail.html']


@user_maintains_package()
def manage(request, owner, package, version, **kwargs):
    kwargs.pop('owner')
    release = get_object_or_404(Package, owner=request.user, name=package).get_release(version)
    
    if not release:
        raise Http404('Version %s does not exist for %s' % (version,
                                                            package,))
    
    kwargs['object_id'] = release.pk
    
    kwargs.setdefault('form_class', ReleaseForm)
    kwargs.setdefault('template_name', 'userpypi/release_manage.html')
    kwargs.setdefault('template_object_name', 'release')
    
    return create_update.update_object(request, **kwargs)

@user_maintains_package()
def manage_metadata(request, owner, package, version, **kwargs):
    kwargs.pop('owner')
    kwargs.setdefault('template_name', 'userpypi/release_manage.html')
    kwargs.setdefault('template_object_name', 'release')
    kwargs.setdefault('extra_context', {})
    kwargs.setdefault('mimetype', settings.DEFAULT_CONTENT_TYPE)
    
    release = get_object_or_404(Package, owner=request.user, name=package).get_release(version)
    
    if not release:
        raise Http404('Version %s does not exist for %s' % (version,
                                                            package,))
    
    if not release.metadata_version in METADATA_FORMS:
        #TODO: Need to change this to a more meaningful error
        raise Http404()
    
    kwargs['extra_context'][kwargs['template_object_name']] = release
    
    form_class = get_class(METADATA_FORMS.get(release.metadata_version))
    
    initial = {}
    multivalue = ('classifier',)
    
    for key, values in release.package_info.iterlists():
        if key in multivalue:
            initial[key] = values
        else:
            initial[key] = '\n'.join(values)
    
    if request.method == 'POST':
        form = form_class(data=request.POST, initial=initial)
        
        if form.is_valid():
            for key, value in form.cleaned_data.iteritems():
                if isinstance(value, basestring):
                    release.package_info[key] = value
                elif hasattr(value, '__iter__'):
                    release.package_info.setlist(key, list(value))
            
            release.save()
            return create_update.redirect(kwargs.get('post_save_redirect',None),
                                          release)
    else:
        form = form_class(initial=initial)
    
    kwargs['extra_context']['form'] = form
    
    return render_to_response(kwargs['template_name'], kwargs['extra_context'],
                              context_instance=RequestContext(request),
                              mimetype=kwargs['mimetype'])

@user_maintains_package()
def manage_files(request, package, version, **kwargs):
    release = get_object_or_404(Package, owner=request.user, name=package).get_release(version)
    
    if not release:
        raise Http404('Version %s does not exist for %s' % (version,
                                                            package,))
    
    kwargs.setdefault('formset_factory_kwargs',{})
    kwargs['formset_factory_kwargs'].setdefault('fields', ('comment',))
    kwargs['formset_factory_kwargs']['extra'] = 0
    
    kwargs.setdefault('formset_factory', inlineformset_factory(Release, Distribution, **kwargs['formset_factory_kwargs']))
    kwargs.setdefault('template_name', 'userpypi/release_manage_files.html')
    kwargs.setdefault('template_object_name', 'release')
    kwargs.setdefault('extra_context',{})
    kwargs.setdefault('mimetype',settings.DEFAULT_CONTENT_TYPE)
    kwargs['extra_context'][kwargs['template_object_name']] = release
    kwargs.setdefault('formset_kwargs',{})
    kwargs['formset_kwargs']['instance'] = release
    kwargs.setdefault('upload_form_factory', DistributionUploadForm)
    
    if request.method == 'POST':
        formset = kwargs['formset_factory'](data=request.POST,
                                            files=request.FILES,
                                            **kwargs['formset_kwargs'])
        if formset.is_valid():
            formset.save()
            formset = kwargs['formset_factory'](**kwargs['formset_kwargs'])
    else:
        formset = kwargs['formset_factory'](**kwargs['formset_kwargs'])
    
    kwargs['extra_context']['formset'] = formset
    kwargs['extra_context'].setdefault('upload_form',
                                       kwargs['upload_form_factory']())
    
    return render_to_response(kwargs['template_name'], kwargs['extra_context'],
                              context_instance=RequestContext(request),
                              mimetype=kwargs['mimetype'])

@user_maintains_package()
def upload_file(request, package, version, **kwargs):
    release = get_object_or_404(Package, owner=request.user, name=package).get_release(version)
    
    if not release:
        raise Http404('Version %s does not exist for %s' % (version,
                                                            package,))
    
    kwargs.setdefault('form_factory', DistributionUploadForm)
    kwargs.setdefault('post_save_redirect', reverse('userpypi-release-manage-files',
                                                    kwargs={'package': package,
                                                            'version': version}))
    kwargs.setdefault('template_name', 'userpypi/release_upload_file.html')
    kwargs.setdefault('template_object_name', 'release')
    kwargs.setdefault('extra_context',{})
    kwargs.setdefault('mimetype',settings.DEFAULT_CONTENT_TYPE)
    kwargs['extra_context'][kwargs['template_object_name']] = release
    
    if request.method == 'POST':
        form = kwargs['form_factory'](data=request.POST, files=request.FILES)
        if form.is_valid():
            dist = form.save(commit=False)
            dist.release = release
            dist.uploader = request.user
            dist.save()
            
            return create_update.redirect(kwargs.get('post_save_redirect'),
                                          release)
    else:
        form = kwargs['form_factory']()
    
    kwargs['extra_context']['form'] = form
    
    return render_to_response(kwargs['template_name'], kwargs['extra_context'],
                              context_instance=RequestContext(request),
                              mimetype=kwargs['mimetype'])
