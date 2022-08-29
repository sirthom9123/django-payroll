from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.template.loader import render_to_string, get_template
from django.http import HttpResponse
from django.conf import settings
from employee.models import Payroll
from xhtml2pdf import pisa
import os
from django.conf import settings
from django.contrib.staticfiles import finders

def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those
    resources
    """
    result = finders.find(uri)
    if result:
            if not isinstance(result, (list, tuple)):
                    result = [result]
            result = list(os.path.realpath(path) for path in result)
            path=result[0]
    else:
            sUrl = settings.STATIC_URL        # Typically /static/
            sRoot = settings.STATIC_ROOT      # Typically /home/userX/project_static/
            mUrl = settings.MEDIA_URL         # Typically /media/
            mRoot = settings.MEDIA_ROOT       # Typically /home/userX/project_static/media/

            if uri.startswith(mUrl):
                    path = os.path.join(mRoot, uri.replace(mUrl, ""))
            elif uri.startswith(sUrl):
                    path = os.path.join(sRoot, uri.replace(sUrl, ""))
            else:
                    return uri

    # make sure that file exists
    if not os.path.isfile(path):
            raise Exception(
                    'media URI must start with %s or %s' % (sUrl, mUrl)
            )
    return path

@staff_member_required
def admin_export_payroll_pdf(request, id):
    payroll = get_object_or_404(Payroll, id=id)

    context = {'payroll': payroll,}
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename=payroll_{payroll.employee.emp_code}.pdf'
    template = get_template('payroll.html')
    html = template.render(context) 
    
    # create pdf
    pisa_status = pisa.CreatePDF(
       html, dest=response, link_callback=link_callback)
    if pisa_status.err:
       return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response