from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.template.loader import get_template
from django.http import HttpResponse
from django.conf import settings
from xhtml2pdf import pisa
import os
from django.contrib.staticfiles import finders

def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those
    resources
    """
    result = finders.find(uri)
    if isinstance(result, (list, tuple)):
        result = next((item for item in result if item), None)
    sUrl = settings.STATIC_URL
    sRoot = settings.STATIC_ROOT
    mUrl = settings.MEDIA_URL
    mRoot = settings.MEDIA_ROOT
    if result:
            path = os.path.realpath(result)
    else:
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

def render_payroll_pdf(payroll):
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'filename=payroll_{payroll.employee.emp_code}.pdf'
    template = get_template("payroll.html")
    html = template.render({"payroll": payroll})
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=link_callback)
    if pisa_status.err:
        return HttpResponse("We had some errors <pre>" + html + "</pre>")
    return response


@staff_member_required
def admin_export_payroll_pdf(request, id):
    from employee.access import can_use_hr
    from employee.payroll_views import payroll_queryset

    if not can_use_hr(request.user):
        return render(request, "hr/no_access.html", status=403)
    payroll = get_object_or_404(payroll_queryset(request.user), id=id)
    return render_payroll_pdf(payroll)